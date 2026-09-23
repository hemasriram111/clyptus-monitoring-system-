from datetime import datetime, timezone, date, timedelta
from typing import List, Optional, Tuple
from sqlalchemy.orm import Session
from fastapi import HTTPException, status
from app.models.all_models import User, UserRole, ActivityLog, ProjectMember
from app.models.attendance import AttendanceRecord, PunchLog, AttendanceStatus, PunchType
from app.schemas.attendance import (
    TodayAttendanceOut,
    PunchLogOut,
    AttendanceRecordOut,
    TeamMemberDailyAttendance,
    TeamAttendanceSnapshot,
)


def get_today_date_str() -> str:
    """Returns today's date in YYYY-MM-DD format based on UTC or local server time."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def calculate_active_minutes(punches: List[PunchLog], is_ongoing: bool = True) -> float:
    """
    Calculates accumulated working minutes from an ordered list of punches.
    Active segments:
      - from CLOCK_IN or BREAK_END
      - to BREAK_START or CLOCK_OUT
    If the last punch is CLOCK_IN or BREAK_END, and is_ongoing=True,
    the active segment runs until now.
    """
    total_seconds = 0.0
    active_start: Optional[datetime] = None

    now = datetime.now(timezone.utc)

    for p in punches:
        p_time = p.punch_time
        if p_time.tzinfo is None:
            p_time = p_time.replace(tzinfo=timezone.utc)

        p_type = p.punch_type

        if p_type in (PunchType.CLOCK_IN.value, PunchType.CLOCK_IN, PunchType.BREAK_END.value, PunchType.BREAK_END):
            if active_start is None:
                active_start = p_time
        elif p_type in (PunchType.BREAK_START.value, PunchType.BREAK_START, PunchType.CLOCK_OUT.value, PunchType.CLOCK_OUT):
            if active_start is not None:
                diff = (p_time - active_start).total_seconds()
                if diff > 0:
                    total_seconds += diff
                active_start = None

    # If still clocked in and currently active
    if active_start is not None and is_ongoing:
        diff = (now - active_start).total_seconds()
        if diff > 0:
            total_seconds += diff

    return round(total_seconds / 60.0, 1)


def record_punch(
    db: Session,
    user: User,
    punch_type: PunchType,
    ip_address: Optional[str] = None,
) -> AttendanceRecord:
    today_str = get_today_date_str()
    now = datetime.now(timezone.utc)

    record = db.query(AttendanceRecord).filter(
        AttendanceRecord.member_id == user.id,
        AttendanceRecord.date == today_str,
    ).first()

    if not record:
        record = AttendanceRecord(
            member_id=user.id,
            date=today_str,
            status=AttendanceStatus.PRESENT.value if punch_type in (PunchType.CLOCK_IN, PunchType.CLOCK_IN.value) else AttendanceStatus.ABSENT.value,
            total_active_minutes=0.0,
        )
        db.add(record)
        db.commit()
        db.refresh(record)

    # Fetch existing punches for today
    existing_punches = db.query(PunchLog).filter(
        PunchLog.attendance_record_id == record.id
    ).order_by(PunchLog.punch_time.asc()).all()

    last_punch = existing_punches[-1] if existing_punches else None
    last_type = last_punch.punch_type if last_punch else None

    # Validate logical punch sequences
    if punch_type in (PunchType.CLOCK_IN, PunchType.CLOCK_IN.value):
        if last_type in (PunchType.CLOCK_IN.value, PunchType.CLOCK_IN, PunchType.BREAK_END.value, PunchType.BREAK_END):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="You are already clocked in.",
            )
        if last_type in (PunchType.BREAK_START.value, PunchType.BREAK_START):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="You are currently on a break. Please resume work (Break End) instead of clocking in.",
            )
        if not record.first_clock_in:
            record.first_clock_in = now
        record.status = AttendanceStatus.PRESENT.value

    elif punch_type in (PunchType.BREAK_START, PunchType.BREAK_START.value):
        if not last_type or last_type in (PunchType.CLOCK_OUT.value, PunchType.CLOCK_OUT):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot take a break. You are not currently clocked in.",
            )
        if last_type in (PunchType.BREAK_START.value, PunchType.BREAK_START):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="You are already on a break.",
            )

    elif punch_type in (PunchType.BREAK_END, PunchType.BREAK_END.value):
        if not last_type or last_type not in (PunchType.BREAK_START.value, PunchType.BREAK_START):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="You are not currently on a break.",
            )

    elif punch_type in (PunchType.CLOCK_OUT, PunchType.CLOCK_OUT.value):
        if not last_type or last_type in (PunchType.CLOCK_OUT.value, PunchType.CLOCK_OUT):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="You have already clocked out or not yet clocked in today.",
            )
        record.last_clock_out = now

    # Create punch log
    punch_val = punch_type.value if hasattr(punch_type, "value") else str(punch_type)
    new_punch = PunchLog(
        attendance_record_id=record.id,
        punch_time=now,
        punch_type=punch_val,
        ip_address=ip_address,
    )
    db.add(new_punch)
    db.commit()

    # Re-calculate total active minutes
    all_punches = db.query(PunchLog).filter(
        PunchLog.attendance_record_id == record.id
    ).order_by(PunchLog.punch_time.asc()).all()

    # Is currently still ongoing (i.e. not clocked out)
    is_still_working = punch_val not in (PunchType.CLOCK_OUT.value, PunchType.CLOCK_OUT, PunchType.BREAK_START.value, PunchType.BREAK_START)
    active_mins = calculate_active_minutes(all_punches, is_ongoing=is_still_working)
    record.total_active_minutes = active_mins

    # Determine status
    if record.last_clock_out:
        if active_mins >= 480:  # 8 hours
            record.status = AttendanceStatus.PRESENT.value
        elif active_mins >= 240:  # 4 hours
            record.status = AttendanceStatus.HALF_DAY.value
        else:
            record.status = AttendanceStatus.HALF_DAY.value if active_mins > 30 else AttendanceStatus.ABSENT.value
    else:
        record.status = AttendanceStatus.PRESENT.value

    # Log activity in ActivityLog
    activity_msg = {
        PunchType.CLOCK_IN.value: f"{user.name} clocked in",
        PunchType.BREAK_START.value: f"{user.name} started a break",
        PunchType.BREAK_END.value: f"{user.name} resumed work from break",
        PunchType.CLOCK_OUT.value: f"{user.name} clocked out (Total: {round(active_mins/60, 1)} hrs)",
    }.get(punch_val, f"{user.name} logged attendance punch: {punch_val}")

    act = ActivityLog(
        user_id=user.id,
        action=activity_msg,
        entity_type="ATTENDANCE",
        entity_id=record.id,
        created_at=now,
    )
    db.add(act)

    db.commit()
    db.refresh(record)
    return record


def get_today_attendance(db: Session, user: User) -> TodayAttendanceOut:
    today_str = get_today_date_str()
    record = db.query(AttendanceRecord).filter(
        AttendanceRecord.member_id == user.id,
        AttendanceRecord.date == today_str,
    ).first()

    if not record:
        return TodayAttendanceOut(
            is_clocked_in=False,
            is_on_break=False,
            last_punch_type=None,
            active_minutes_today=0.0,
            first_clock_in=None,
            last_clock_out=None,
            status=AttendanceStatus.ABSENT.value,
            record=None,
            punches=[],
        )

    punches = db.query(PunchLog).filter(
        PunchLog.attendance_record_id == record.id
    ).order_by(PunchLog.punch_time.asc()).all()

    last_punch = punches[-1] if punches else None
    last_type = last_punch.punch_type if last_punch else None

    is_clocked_in = last_type in (
        PunchType.CLOCK_IN.value,
        PunchType.CLOCK_IN,
        PunchType.BREAK_START.value,
        PunchType.BREAK_START,
        PunchType.BREAK_END.value,
        PunchType.BREAK_END,
    ) and last_type not in (PunchType.CLOCK_OUT.value, PunchType.CLOCK_OUT)

    is_on_break = last_type in (PunchType.BREAK_START.value, PunchType.BREAK_START)

    # Live calculate current active minutes
    live_active_mins = calculate_active_minutes(punches, is_ongoing=(is_clocked_in and not is_on_break))

    punches_out = [PunchLogOut.model_validate(p) for p in punches]
    record_out = AttendanceRecordOut(
        id=record.id,
        member_id=record.member_id,
        date=record.date,
        first_clock_in=record.first_clock_in,
        last_clock_out=record.last_clock_out,
        status=record.status,
        total_active_minutes=live_active_mins,
        punches=punches_out,
        member_name=user.name,
        member_email=user.email,
    )

    return TodayAttendanceOut(
        is_clocked_in=is_clocked_in,
        is_on_break=is_on_break,
        last_punch_type=last_type,
        active_minutes_today=live_active_mins,
        first_clock_in=record.first_clock_in,
        last_clock_out=record.last_clock_out,
        status=record.status,
        record=record_out,
        punches=punches_out,
    )


def get_member_monthly_records(
    db: Session,
    user_id: int,
    year: int,
    month: int,
) -> List[AttendanceRecordOut]:
    prefix = f"{year:04d}-{month:02d}"
    records = db.query(AttendanceRecord).filter(
        AttendanceRecord.member_id == user_id,
        AttendanceRecord.date.like(f"{prefix}%"),
    ).order_by(AttendanceRecord.date.desc()).all()

    result = []
    user = db.query(User).filter(User.id == user_id).first()
    u_name = user.name if user else None
    u_email = user.email if user else None

    for r in records:
        punches = [PunchLogOut.model_validate(p) for p in r.punches]
        result.append(
            AttendanceRecordOut(
                id=r.id,
                member_id=r.member_id,
                date=r.date,
                first_clock_in=r.first_clock_in,
                last_clock_out=r.last_clock_out,
                status=r.status,
                total_active_minutes=r.total_active_minutes,
                punches=punches,
                member_name=u_name,
                member_email=u_email,
            )
        )
    return result


def get_team_daily_snapshot(
    db: Session,
    target_date: Optional[str] = None,
) -> TeamAttendanceSnapshot:
    date_str = target_date or get_today_date_str()
    is_today = (date_str == get_today_date_str())

    members = db.query(User).filter(User.is_active == True).all()

    online_count = 0
    on_break_count = 0
    clocked_out_count = 0
    not_logged_in_count = 0

    items: List[TeamMemberDailyAttendance] = []

    for m in members:
        # Get assigned role if member of any project
        pm = db.query(ProjectMember).filter(ProjectMember.user_id == m.id).first()
        assigned_role = pm.assigned_role if pm else m.role

        record = db.query(AttendanceRecord).filter(
            AttendanceRecord.member_id == m.id,
            AttendanceRecord.date == date_str,
        ).first()

        if not record:
            not_logged_in_count += 1
            items.append(
                TeamMemberDailyAttendance(
                    member_id=m.id,
                    name=m.name,
                    email=m.email,
                    assigned_role=assigned_role,
                    profile_image=m.profile_image,
                    current_status="NOT_LOGGED_IN",
                    first_clock_in=None,
                    last_clock_out=None,
                    active_minutes=0.0,
                    record_status=AttendanceStatus.ABSENT.value,
                )
            )
        else:
            punches = db.query(PunchLog).filter(
                PunchLog.attendance_record_id == record.id
            ).order_by(PunchLog.punch_time.asc()).all()

            last_punch = punches[-1] if punches else None
            last_type = last_punch.punch_type if last_punch else None

            if not last_type:
                current_status = "NOT_LOGGED_IN"
                not_logged_in_count += 1
            elif last_type in (PunchType.CLOCK_OUT.value, PunchType.CLOCK_OUT):
                current_status = "CLOCKED_OUT"
                clocked_out_count += 1
            elif last_type in (PunchType.BREAK_START.value, PunchType.BREAK_START):
                current_status = "ON_BREAK"
                on_break_count += 1
            else:
                current_status = "ONLINE"
                online_count += 1

            # calculate active minutes
            is_ongoing = is_today and current_status == "ONLINE"
            active_mins = calculate_active_minutes(punches, is_ongoing=is_ongoing)

            items.append(
                TeamMemberDailyAttendance(
                    member_id=m.id,
                    name=m.name,
                    email=m.email,
                    assigned_role=assigned_role,
                    profile_image=m.profile_image,
                    current_status=current_status,
                    first_clock_in=record.first_clock_in,
                    last_clock_out=record.last_clock_out,
                    active_minutes=active_mins,
                    record_status=record.status,
                )
            )

    return TeamAttendanceSnapshot(
        total_members=len(members),
        online_count=online_count,
        on_break_count=on_break_count,
        clocked_out_count=clocked_out_count,
        not_logged_in_count=not_logged_in_count,
        members=items,
    )


def get_team_attendance_report(
    db: Session,
    start_date: str,
    end_date: str,
    member_id: Optional[int] = None,
) -> List[AttendanceRecordOut]:
    q = db.query(AttendanceRecord).filter(
        AttendanceRecord.date >= start_date,
        AttendanceRecord.date <= end_date,
    )

    if member_id:
        q = q.filter(AttendanceRecord.member_id == member_id)

    records = q.order_by(AttendanceRecord.date.desc()).all()

    user_map = {u.id: u for u in db.query(User).all()}

    result = []
    for r in records:
        u = user_map.get(r.member_id)
        punches = [PunchLogOut.model_validate(p) for p in r.punches]
        result.append(
            AttendanceRecordOut(
                id=r.id,
                member_id=r.member_id,
                date=r.date,
                first_clock_in=r.first_clock_in,
                last_clock_out=r.last_clock_out,
                status=r.status,
                total_active_minutes=r.total_active_minutes,
                punches=punches,
                member_name=u.name if u else "User",
                member_email=u.email if u else "",
            )
        )
    return result
