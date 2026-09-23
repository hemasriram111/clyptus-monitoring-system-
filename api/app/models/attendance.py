from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Float
from sqlalchemy.orm import relationship
import enum
from app.core.database import Base


class AttendanceStatus(str, enum.Enum):
    PRESENT = "PRESENT"
    ABSENT = "ABSENT"
    HALF_DAY = "HALF_DAY"
    ON_LEAVE = "ON_LEAVE"


class PunchType(str, enum.Enum):
    CLOCK_IN = "CLOCK_IN"
    CLOCK_OUT = "CLOCK_OUT"
    BREAK_START = "BREAK_START"
    BREAK_END = "BREAK_END"


class AttendanceRecord(Base):
    __tablename__ = "attendance_records"

    id = Column(Integer, primary_key=True, index=True)
    member_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    date = Column(String(10), nullable=False, index=True)  # Format: YYYY-MM-DD
    first_clock_in = Column(DateTime, nullable=True)
    last_clock_out = Column(DateTime, nullable=True)
    status = Column(String(50), nullable=False, default=AttendanceStatus.ABSENT.value)
    total_active_minutes = Column(Float, nullable=False, default=0.0)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    # Relationships
    member = relationship("User", foreign_keys=[member_id])
    punches = relationship("PunchLog", back_populates="attendance_record", cascade="all, delete-orphan", order_by="PunchLog.punch_time.asc()")


class PunchLog(Base):
    __tablename__ = "punch_logs"

    id = Column(Integer, primary_key=True, index=True)
    attendance_record_id = Column(Integer, ForeignKey("attendance_records.id", ondelete="CASCADE"), nullable=False, index=True)
    punch_time = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    punch_type = Column(String(50), nullable=False)  # CLOCK_IN, CLOCK_OUT, BREAK_START, BREAK_END
    ip_address = Column(String(100), nullable=True)

    # Relationships
    attendance_record = relationship("AttendanceRecord", back_populates="punches")
