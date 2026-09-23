from typing import List
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.models.all_models import Task, Project, User
from app.schemas.analytics import CalendarEvent
from app.services.auth_service import get_current_user

router = APIRouter(prefix="/calendar", tags=["Calendar"])


@router.get("/events", response_model=List[CalendarEvent])
def get_calendar_events(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    events: List[CalendarEvent] = []

    # Fetch projects
    projects = db.query(Project).all()
    for p in projects:
        if p.start_date:
            events.append(
                CalendarEvent(
                    id=f"proj-start-{p.id}",
                    title=f"Project Start: {p.name}",
                    type="PROJECT_START",
                    date=p.start_date.isoformat(),
                    project_name=p.name,
                )
            )
        if p.end_date:
            events.append(
                CalendarEvent(
                    id=f"proj-end-{p.id}",
                    title=f"Project End: {p.name}",
                    type="PROJECT_END",
                    date=p.end_date.isoformat(),
                    project_name=p.name,
                )
            )

    # Fetch tasks
    if current_user.role == "TEAM_LEAD":
        tasks = db.query(Task).filter(Task.due_date.isnot(None)).all()
    else:
        tasks = db.query(Task).filter(Task.assigned_to == current_user.id, Task.due_date.isnot(None)).all()

    for t in tasks:
        events.append(
            CalendarEvent(
                id=f"task-due-{t.id}",
                title=f"Task Due: {t.title}",
                type="TASK_DEADLINE",
                date=t.due_date.isoformat(),
                status=t.status,
                priority=t.priority,
                project_name=t.project.name if t.project else None,
            )
        )

    return events
