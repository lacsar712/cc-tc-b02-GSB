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


class RainGateState(Base):
    """雨量闸开关：全局单行（id=1）。阈值只存后端，前端无权自编。"""

    __tablename__ = "rain_gate_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    is_open: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    rain_limit_mm: Mapped[float | None] = mapped_column(Float, nullable=True)
    opened_by: Mapped[str | None] = mapped_column(String, nullable=True)
    opened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class GateEvent(Base):
    """开闸/关闸流水。"""

    __tablename__ = "rain_gate_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    action: Mapped[str] = mapped_column(String, nullable=False)  # open / close
    rain_limit_mm: Mapped[float | None] = mapped_column(Float, nullable=True)
    operator: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # 关闸时回写本次开闸持续秒数；开闸行该列为空
    duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)


class GateRejection(Base):
    """雨量越界退回流水：必须与真实拒收同事务写入。"""

    __tablename__ = "rain_gate_rejections"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    chainage: Mapped[str] = mapped_column(String, nullable=False)
    delta_mm: Mapped[float] = mapped_column(Float, nullable=False)
    rain_limit_mm: Mapped[float] = mapped_column(Float, nullable=False)
    reason: Mapped[str] = mapped_column(String, nullable=False)
    rejected_by: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


def gate_state_dict(row: RainGateState) -> dict:
    return {
        "is_open": row.is_open,
        "rain_limit_mm": row.rain_limit_mm,
        "opened_by": row.opened_by,
        "opened_at": row.opened_at.isoformat() if row.opened_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def gate_event_dict(row: GateEvent) -> dict:
    return {
        "id": row.id,
        "action": row.action,
        "rain_limit_mm": row.rain_limit_mm,
        "operator": row.operator,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "duration_seconds": row.duration_seconds,
    }


def gate_rejection_dict(row: GateRejection) -> dict:
    return {
        "id": row.id,
        "chainage": row.chainage,
        "delta_mm": row.delta_mm,
        "rain_limit_mm": row.rain_limit_mm,
        "reason": row.reason,
        "rejected_by": row.rejected_by,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }
