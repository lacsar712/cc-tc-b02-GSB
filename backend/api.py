import math
import os
from datetime import datetime, timedelta, timezone
from functools import wraps

from flask import Flask, g, jsonify, request
from jose import JWTError, jwt
from passlib.context import CryptContext

from claimer import start as start_claimer
from models import (
    Base,
    ConvergenceLog,
    RainGateEvent,
    RainGateState,
    SessionLocal,
    engine,
    gate_event_dict,
    gate_state_dict,
    row_dict,
)

SECRET = os.environ.get("JWT_SECRET", "tunnelconv-dev-secret")
pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")
USERS = {
    "surveyor": {"role": "writer", "password_hash": pwd.hash("surv123456")},
    "inspector": {"role": "reader", "password_hash": pwd.hash("insp123456")},
}

app = Flask(__name__)


def seed():
    Base.metadata.create_all(engine)
    db = SessionLocal()
    try:
        if db.query(ConvergenceLog).count() == 0:
            now = datetime.now(timezone.utc)
            for chainage, delta, expect in (("K12+180", 1.2, "合格"), ("K18+040", 5.6, "超限")):
                from rules import judge

                verdict, reason = judge(delta)
                assert verdict == expect
                db.add(
                    ConvergenceLog(
                        chainage=chainage,
                        delta_mm=delta,
                        status="done",
                        verdict=verdict,
                        reason=reason,
                        created_by="surveyor",
                        created_at=now,
                        processed_at=now,
                    )
                )
        if db.query(RainGateState).count() == 0:
            db.add(
                RainGateState(
                    threshold_mm=None,
                    is_open=False,
                    opened_by=None,
                    opened_at=None,
                    closed_at=None,
                    updated_at=datetime.now(timezone.utc),
                )
            )
        db.commit()
    finally:
        db.close()


seed()
start_claimer()


def current_user():
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return None
    try:
        payload = jwt.decode(auth[7:].strip(), SECRET, algorithms=["HS256"])
    except JWTError:
        return None
    sub = payload.get("sub")
    if sub not in USERS:
        return None
    return {"username": sub, "role": payload.get("role")}


def require_login(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        user = current_user()
        if user is None:
            return jsonify({"detail": "未登录"}), 401
        g.user = user
        return fn(*args, **kwargs)

    return wrapper


def require_writer(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        user = current_user()
        if user is None:
            return jsonify({"detail": "未登录"}), 401
        if user["role"] != "writer":
            return jsonify({"detail": "仅测量员可操作"}), 403
        g.user = user
        return fn(*args, **kwargs)

    return wrapper


def as_utc(dt):
    """数据库可能返回 naive 时间（如 SQLite），统一补上 UTC。"""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def parse_number(value, field):
    """把请求里的数字字段解析成有限 float；空值/非法值抛 ValueError（中文信息）。"""
    if value is None or (isinstance(value, str) and not value.strip()):
        raise ValueError(f"{field}不能为空")
    try:
        num = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{field}必须是数字")
    if not math.isfinite(num):
        raise ValueError(f"{field}必须是有限数字")
    return num


def get_gate_state(db):
    return db.query(RainGateState).order_by(RainGateState.id).first()


@app.get("/api/health")
def health():
    return jsonify({"status": "ok", "service": "tunnel-convergence-desk"})


@app.post("/api/auth/login")
def login():
    body = request.get_json(silent=True) or {}
    username = (body.get("username") or "").strip()
    password = body.get("password") or ""
    user = USERS.get(username)
    if not user or not pwd.verify(password, user["password_hash"]):
        return jsonify({"detail": "用户名或密码错误"}), 401
    exp = datetime.now(timezone.utc) + timedelta(hours=8)
    token = jwt.encode(
        {"sub": username, "role": user["role"], "exp": exp}, SECRET, algorithm="HS256"
    )
    return jsonify({"access_token": token, "username": username, "role": user["role"]})


@app.get("/api/logs")
@require_login
def list_logs():
    db = SessionLocal()
    try:
        rows = db.query(ConvergenceLog).order_by(ConvergenceLog.id.desc()).all()
        return jsonify([row_dict(r) for r in rows])
    finally:
        db.close()


@app.post("/api/logs")
@require_writer
def create_log():
    body = request.get_json(silent=True) or {}
    chainage = (body.get("chainage") or "").strip()
    if not chainage:
        return jsonify({"detail": "桩号不能为空"}), 400
    try:
        delta_mm = parse_number(body.get("delta_mm"), "收敛值")
    except ValueError as exc:
        return jsonify({"detail": str(exc)}), 400

    rainfall_raw = body.get("rainfall_mm")
    db = SessionLocal()
    try:
        # 锁住雨量闸单行状态，保证“判定拒收”和“写拒收流水/插单”在同一事务里
        gate = get_gate_state(db)
        if gate is None:
            db.rollback()
            return jsonify({"detail": "雨量闸状态未初始化"}), 500
        db.refresh(gate, with_for_update=True)

        rainfall_mm = None
        if gate.is_open:
            try:
                rainfall_mm = parse_number(rainfall_raw, "洞口雨量")
                if rainfall_mm < 0:
                    raise ValueError("洞口雨量不能为负")
            except ValueError as exc:
                db.rollback()
                return jsonify({"detail": str(exc)}), 400
            if rainfall_mm > float(gate.threshold_mm):
                detail = (
                    f"洞口雨量 {rainfall_mm} mm 超过雨量上限 {gate.threshold_mm} mm，"
                    f"整份报送退回：桩号 {chainage}，收敛 {delta_mm} mm"
                )
                # 真实拒收：不插报送单，只在同一事务写拒收流水
                db.add(
                    RainGateEvent(
                        kind="reject",
                        threshold_mm=gate.threshold_mm,
                        rainfall_mm=rainfall_mm,
                        chainage=chainage,
                        delta_mm=delta_mm,
                        detail=detail,
                        actor=g.user["username"],
                        created_at=datetime.now(timezone.utc),
                    )
                )
                db.commit()
                return jsonify({"detail": detail, "rejected": True}), 403

        row = ConvergenceLog(
            chainage=chainage,
            delta_mm=delta_mm,
            status="pending",
            created_by=g.user["username"],
            created_at=datetime.now(timezone.utc),
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return jsonify(row_dict(row)), 201
    finally:
        db.close()


@app.get("/api/gate")
@require_login
def get_gate():
    db = SessionLocal()
    try:
        gate = get_gate_state(db)
        events = (
            db.query(RainGateEvent)
            .order_by(RainGateEvent.id.desc())
            .limit(100)
            .all()
        )
        return jsonify(
            {
                "state": gate_state_dict(gate),
                "events": [gate_event_dict(e) for e in events],
            }
        )
    finally:
        db.close()


@app.post("/api/gate/open")
@require_writer
def open_gate():
    body = request.get_json(silent=True) or {}
    try:
        threshold = parse_number(body.get("threshold_mm"), "雨量上限")
    except ValueError as exc:
        return jsonify({"detail": str(exc)}), 400
    if threshold < 0:
        return jsonify({"detail": "雨量上限不能为负"}), 400

    db = SessionLocal()
    try:
        gate = get_gate_state(db)
        if gate is None:
            return jsonify({"detail": "雨量闸状态未初始化"}), 500
        db.refresh(gate, with_for_update=True)
        now = datetime.now(timezone.utc)
        if gate.is_open:
            return jsonify({"detail": "雨量闸已处于开闸状态", "state": gate_state_dict(gate)}), 409
        gate.threshold_mm = threshold
        gate.is_open = True
        gate.opened_by = g.user["username"]
        gate.opened_at = now
        gate.closed_at = None
        gate.updated_at = now
        detail = f"开闸：雨量上限设为 {threshold} mm，越界报送整份退回"
        db.add(
            RainGateEvent(
                kind="open",
                threshold_mm=threshold,
                detail=detail,
                actor=g.user["username"],
                created_at=now,
            )
        )
        db.commit()
        db.refresh(gate)
        return jsonify({"state": gate_state_dict(gate)}), 200
    finally:
        db.close()


@app.post("/api/gate/close")
@require_writer
def close_gate():
    db = SessionLocal()
    try:
        gate = get_gate_state(db)
        if gate is None:
            return jsonify({"detail": "雨量闸状态未初始化"}), 500
        db.refresh(gate, with_for_update=True)
        now = datetime.now(timezone.utc)
        if not gate.is_open:
            return jsonify({"detail": "雨量闸未开闸", "state": gate_state_dict(gate)}), 409
        threshold = gate.threshold_mm
        gate.is_open = False
        gate.closed_at = now
        gate.updated_at = now
        duration = (
            (now - as_utc(gate.opened_at)).total_seconds() if gate.opened_at else None
        )
        dur_text = f"，本次开闸持续 {duration:.0f} 秒" if duration is not None else ""
        detail = f"关闸：新单不再拦截（雨量上限 {threshold} mm{dur_text}）"
        db.add(
            RainGateEvent(
                kind="close",
                threshold_mm=threshold,
                detail=detail,
                actor=g.user["username"],
                created_at=now,
            )
        )
        db.commit()
        db.refresh(gate)
        return jsonify({"state": gate_state_dict(gate)}), 200
    finally:
        db.close()
