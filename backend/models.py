import os
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, Integer, String, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

DSN = os.environ.get("DATABASE_URL", "postgresql://app:app@localhost:54401/tunnelconv")
engine = create_engine(DSN, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine)


class Base(DeclarativeBase):
    pass


class ConvergenceLog(Base):
    __tablename__ = "convergence_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    chainage: Mapped[str] = mapped_column(String, nullable=False)
    delta_mm: Mapped[float] = mapped_column(Float, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="pending")
    verdict: Mapped[str | None] = mapped_column(String, nullable=True)
    reason: Mapped[str | None] = mapped_column(String, nullable=True)
    created_by: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class RainGateState(Base):
    """雨量闸单行状态：阈值、开/关状态与时间戳。"""

    __tablename__ = "rain_gate_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    threshold_mm: Mapped[float | None] = mapped_column(Float, nullable=True)
    is_open: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    opened_by: Mapped[str | None] = mapped_column(String, nullable=True)
    opened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class RainGateEvent(Base):
    """雨量闸流水：开闸、关闸、越界拒收都写这里。"""

    __tablename__ = "rain_gate_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[str] = mapped_column(String, nullable=False)  # open / close / reject
    threshold_mm: Mapped[float | None] = mapped_column(Float, nullable=True)
    rainfall_mm: Mapped[float | None] = mapped_column(Float, nullable=True)
    chainage: Mapped[str | None] = mapped_column(String, nullable=True)
    delta_mm: Mapped[float | None] = mapped_column(Float, nullable=True)
    detail: Mapped[str] = mapped_column(String, nullable=False)
    actor: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


def gate_state_dict(row: RainGateState) -> dict:
    # 上次开闸持续时长：仅在已关闸（有完整开/关时间）时给出秒数
    last_open_seconds = None
    if row.opened_at is not None and row.closed_at is not None and not row.is_open:
        opened = row.opened_at
        closed = row.closed_at
        if opened.tzinfo is None:
            opened = opened.replace(tzinfo=timezone.utc)
        if closed.tzinfo is None:
            closed = closed.replace(tzinfo=timezone.utc)
        last_open_seconds = (closed - opened).total_seconds()
    return {
        "threshold_mm": row.threshold_mm,
        "is_open": row.is_open,
        "opened_by": row.opened_by,
        "opened_at": row.opened_at.isoformat() if row.opened_at else None,
        "closed_at": row.closed_at.isoformat() if row.closed_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        "last_open_seconds": last_open_seconds,
    }


def gate_event_dict(row: RainGateEvent) -> dict:
    kind_cn = {"open": "开闸", "close": "关闸", "reject": "越界拒收"}.get(row.kind, row.kind)
    return {
        "id": row.id,
        "kind": row.kind,
        "kind_cn": kind_cn,
        "threshold_mm": row.threshold_mm,
        "rainfall_mm": row.rainfall_mm,
        "chainage": row.chainage,
        "delta_mm": row.delta_mm,
        "detail": row.detail,
        "actor": row.actor,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def row_dict(row: ConvergenceLog) -> dict:
    return {
        "id": row.id,
        "chainage": row.chainage,
        "delta_mm": row.delta_mm,
        "status": row.status,
        "verdict": row.verdict,
        "reason": row.reason,
        "created_by": row.created_by,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "processed_at": row.processed_at.isoformat() if row.processed_at else None,
    }
