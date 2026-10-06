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
    GateEvent,
    GateRejection,
    RainGateState,
    SessionLocal,
    engine,
    gate_event_dict,
    gate_rejection_dict,
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
        if db.query(ConvergenceLog).count() > 0:
            return
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
        if db.get(RainGateState, 1) is None:
            db.add(RainGateState(id=1, is_open=False))
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
            return jsonify({"detail": "仅测量员可执行此操作"}), 403
        g.user = user
        return fn(*args, **kwargs)

    return wrapper


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
        delta_mm = float(body.get("delta_mm"))
    except (TypeError, ValueError):
        return jsonify({"detail": "收敛值必须是数字"}), 400
    if not math.isfinite(delta_mm):
        return jsonify({"detail": "收敛值必须是数字"}), 400
    db = SessionLocal()
    try:
        # 行锁取闸状态：闸开且越界 -> 整份退回，并与真实拒收同事务写退回流水
        gate = db.get(RainGateState, 1, with_for_update=True)
        if gate is not None and gate.is_open:
            limit = float(gate.rain_limit_mm)
            if abs(delta_mm) > limit:
                reason = f"雨量闸开启（上限 {limit} mm），读数 {delta_mm} mm 越界，报送整份退回"
                rejection = GateRejection(
                    chainage=chainage,
                    delta_mm=delta_mm,
                    rain_limit_mm=limit,
                    reason=reason,
                    rejected_by=g.user["username"],
                    created_at=datetime.now(timezone.utc),
                )
                db.add(rejection)
                db.commit()
                db.refresh(rejection)
                return (
                    jsonify({"detail": reason, "rejection": gate_rejection_dict(rejection)}),
                    422,
                )
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
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


@app.get("/api/rain-gate")
@require_login
def get_rain_gate():
    db = SessionLocal()
    try:
        gate = db.get(RainGateState, 1)
        last_close = (
            db.query(GateEvent)
            .filter(GateEvent.action == "close")
            .order_by(GateEvent.id.desc())
            .first()
        )
        payload = gate_state_dict(gate)
        payload["last_open_duration_seconds"] = (
            last_close.duration_seconds if last_close else None
        )
        return jsonify(payload)
    finally:
        db.close()


@app.post("/api/rain-gate/open")
@require_writer
def open_rain_gate():
    body = request.get_json(silent=True) or {}
    raw = body.get("rain_limit_mm")
    # 阈值留空不许开闸；阈值必须由测量员在专页写入后端，前端不得自编
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        return jsonify({"detail": "雨量阈值不能为空，留空不许开闸"}), 400
    try:
        limit = float(raw)
    except (TypeError, ValueError):
        return jsonify({"detail": "雨量阈值必须是数字"}), 400
    if not math.isfinite(limit) or limit <= 0:
        return jsonify({"detail": "雨量阈值必须是大于 0 的数字"}), 400

    now = datetime.now(timezone.utc)
    db = SessionLocal()
    try:
        gate = db.get(RainGateState, 1, with_for_update=True)
        if gate is None:
            gate = RainGateState(id=1)
            db.add(gate)
            db.flush()
        if gate.is_open:
            return jsonify({"detail": "雨量闸已处于开启状态"}), 409
        gate.is_open = True
        gate.rain_limit_mm = limit
        gate.opened_by = g.user["username"]
        gate.opened_at = now
        gate.updated_at = now
        event = GateEvent(
            action="open",
            rain_limit_mm=limit,
            operator=g.user["username"],
            created_at=now,
        )
        db.add(event)
        db.commit()
        db.refresh(event)
        return jsonify(gate_event_dict(event)), 201
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


@app.post("/api/rain-gate/close")
@require_writer
def close_rain_gate():
    now = datetime.now(timezone.utc)
    db = SessionLocal()
    try:
        gate = db.get(RainGateState, 1, with_for_update=True)
        if gate is None or not gate.is_open:
            return jsonify({"detail": "雨量闸未开启"}), 409
        duration = None
        if gate.opened_at is not None:
            opened_at = gate.opened_at
            if opened_at.tzinfo is None:  # SQLite 读回为 naive，按 UTC 处理
                opened_at = opened_at.replace(tzinfo=timezone.utc)
            duration = (now - opened_at).total_seconds()
        event = GateEvent(
            action="close",
            rain_limit_mm=gate.rain_limit_mm,
            operator=g.user["username"],
            created_at=now,
            duration_seconds=duration,
        )
        db.add(event)
        gate.is_open = False
        gate.rain_limit_mm = None
        gate.opened_by = None
        gate.opened_at = None
        gate.updated_at = now
        db.commit()
        db.refresh(event)
        return jsonify(gate_event_dict(event)), 200
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


@app.get("/api/rain-gate/journal")
@require_login
def rain_gate_journal():
    """流水：开/关闸记录与越界退回记录按时间合并，新的在前。"""
    db = SessionLocal()
    try:
        events = db.query(GateEvent).order_by(GateEvent.id.desc()).all()
        rejections = db.query(GateRejection).order_by(GateRejection.id.desc()).all()
        items = []
        for e in events:
            d = gate_event_dict(e)
            d["kind"] = "gate"
            items.append(d)
        for r in rejections:
            d = gate_rejection_dict(r)
            d["kind"] = "rejection"
            d["operator"] = d.pop("rejected_by")
            items.append(d)
        items.sort(key=lambda x: x["created_at"] or "", reverse=True)
        return jsonify(items)
    finally:
        db.close()
