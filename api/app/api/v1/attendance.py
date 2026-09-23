from typing import List, Optional
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, Request, Query, status
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.models.all_models import User
from app.schemas.attendance import (
    PunchRequest,
    AttendanceRecordOut,
    TodayAttendanceOut,
    TeamAttendanceSnapshot,
)
from app.services.auth_service import get_current_user, get_current_team_lead
from app.services.attendance_service import (
    record_punch,
    get_today_attendance,
    get_member_monthly_records,
    get_team_daily_snapshot,
    get_team_attendance_report,
)

router = APIRouter(prefix="/attendance", tags=["Attendance"])


@router.post("/punch", response_model=TodayAttendanceOut)
def punch_attendance(
    req: Request,
    punch_in: PunchRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ip_addr = req.client.host if req.client else None
    record_punch(db=db, user=current_user, punch_type=punch_in.punch_type, ip_address=ip_addr)
    return get_today_attendance(db=db, user=current_user)


@router.get("/me/today", response_model=TodayAttendanceOut)
def get_my_today_attendance(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return get_today_attendance(db=db, user=current_user)


@router.get("/me/monthly", response_model=List[AttendanceRecordOut])
def get_my_monthly_attendance(
    year: Optional[int] = Query(None, description="Year (YYYY)"),
    month: Optional[int] = Query(None, description="Month (1-12)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    now = datetime.now(timezone.utc)
    target_year = year or now.year
    target_month = month or now.month
    return get_member_monthly_records(
        db=db,
        user_id=current_user.id,
        year=target_year,
        month=target_month,
    )


@router.get("/team/daily", response_model=TeamAttendanceSnapshot)
def get_team_daily_attendance(
    date: Optional[str] = Query(None, description="Date in YYYY-MM-DD format"),
    db: Session = Depends(get_db),
    current_lead: User = Depends(get_current_team_lead),
):
    return get_team_daily_snapshot(db=db, target_date=date)


@router.get("/team/report", response_model=List[AttendanceRecordOut])
def get_team_report(
    start_date: str = Query(..., description="Start date (YYYY-MM-DD)"),
    end_date: str = Query(..., description="End date (YYYY-MM-DD)"),
    member_id: Optional[int] = Query(None, description="Filter by member ID"),
    db: Session = Depends(get_db),
    current_lead: User = Depends(get_current_team_lead),
):
    return get_team_attendance_report(
        db=db,
        start_date=start_date,
        end_date=end_date,
        member_id=member_id,
    )
