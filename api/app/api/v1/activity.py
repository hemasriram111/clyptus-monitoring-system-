from typing import List, Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.models.all_models import ActivityLog, User
from app.schemas.activity import ActivityLogOut
from app.services.auth_service import get_current_user

router = APIRouter(prefix="/activity", tags=["Activity Logs"])


@router.get("", response_model=List[ActivityLogOut])
def get_activity_feed(
    project_id: Optional[int] = Query(None, description="Filter by project"),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = db.query(ActivityLog)
    if project_id:
        q = q.filter(ActivityLog.project_id == project_id)

    logs = q.order_by(ActivityLog.created_at.desc()).limit(limit).all()
    return logs
