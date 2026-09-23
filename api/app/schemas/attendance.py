from datetime import datetime, timezone
from typing import Optional, List
from pydantic import BaseModel, ConfigDict, field_serializer
from app.models.attendance import PunchType, AttendanceStatus


class PunchRequest(BaseModel):
    punch_type: PunchType


class PunchLogOut(BaseModel):
    id: int
    attendance_record_id: int
    punch_time: datetime
    punch_type: str
    ip_address: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)

    @field_serializer("punch_time")
    def serialize_punch_time(self, dt: datetime, _info):
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.isoformat()


class AttendanceRecordOut(BaseModel):
    id: int
    member_id: int
    date: str
    first_clock_in: Optional[datetime] = None
    last_clock_out: Optional[datetime] = None
    status: str
    total_active_minutes: float
    punches: List[PunchLogOut] = []
    member_name: Optional[str] = None
    member_email: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)

    @field_serializer("first_clock_in", "last_clock_out")
    def serialize_datetimes(self, dt: Optional[datetime], _info):
        if dt is None:
            return None
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.isoformat()


class TodayAttendanceOut(BaseModel):
    is_clocked_in: bool
    is_on_break: bool
    last_punch_type: Optional[str] = None
    active_minutes_today: float
    first_clock_in: Optional[datetime] = None
    last_clock_out: Optional[datetime] = None
    status: str
    record: Optional[AttendanceRecordOut] = None
    punches: List[PunchLogOut] = []


class TeamMemberDailyAttendance(BaseModel):
    member_id: int
    name: str
    email: str
    assigned_role: Optional[str] = None
    profile_image: Optional[str] = None
    current_status: str  # ONLINE, ON_BREAK, CLOCKED_OUT, NOT_LOGGED_IN
    first_clock_in: Optional[datetime] = None
    last_clock_out: Optional[datetime] = None
    active_minutes: float
    record_status: str  # PRESENT, ABSENT, HALF_DAY, ON_LEAVE

    @field_serializer("first_clock_in", "last_clock_out")
    def serialize_datetimes(self, dt: Optional[datetime], _info):
        if dt is None:
            return None
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.isoformat()


class TeamAttendanceSnapshot(BaseModel):
    total_members: int
    online_count: int
    on_break_count: int
    clocked_out_count: int
    not_logged_in_count: int
    members: List[TeamMemberDailyAttendance]
