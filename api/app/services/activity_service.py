from typing import Optional
from sqlalchemy.orm import Session
from app.models.all_models import ActivityLog


def log_activity(
    db: Session,
    user_id: int,
    action: str,
    entity_type: str,
    project_id: Optional[int] = None,
    entity_id: Optional[int] = None
) -> ActivityLog:
    log = ActivityLog(
        project_id=project_id,
        user_id=user_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
    )
    db.add(log)
    db.commit()
    db.refresh(log)
    return log
