from typing import List, Dict, Any
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.core.database import get_db
from app.models.all_models import (
    User,
    UserRole,
    Project,
    ProjectMember,
    Task,
    TaskStatus,
    TaskPriority,
    ActivityLog,
    Notification,
)
from app.schemas.analytics import LeadDashboardOut, MemberDashboardOut, AnalyticsOut, MemberProgressItem
from app.schemas.task import TaskOut
from app.schemas.activity import ActivityLogOut
from app.services.auth_service import get_current_user, get_current_team_lead
from app.services.task_service import is_task_overdue

router = APIRouter(prefix="/analytics", tags=["Dashboard & Analytics"])


@router.get("/lead-dashboard", response_model=LeadDashboardOut)
def get_lead_dashboard(
    db: Session = Depends(get_db),
    current_lead: User = Depends(get_current_team_lead),
):
    total_members = db.query(User).filter(User.role == UserRole.TEAM_MEMBER.value).count()
    total_tasks = db.query(Task).count()
    completed_tasks = db.query(Task).filter(Task.status == TaskStatus.COMPLETED.value).count()
    in_progress_tasks = db.query(Task).filter(Task.status == TaskStatus.IN_PROGRESS.value).count()
    pending_tasks = db.query(Task).filter(Task.status == TaskStatus.TODO.value).count()

    # Overdue tasks
    all_tasks = db.query(Task).all()
    overdue_tasks_list = [t for t in all_tasks if is_task_overdue(t)]
    overdue_count = len(overdue_tasks_list)

    # Project progress calculation across all tasks
    if total_tasks == 0:
        overall_progress = 0
    else:
        overall_progress = int(round((completed_tasks / total_tasks) * 100))

    # Team Member progress calculation
    members = db.query(User).filter(User.role == UserRole.TEAM_MEMBER.value).all()
    member_progress_list = []
    for m in members:
        m_total = db.query(Task).filter(Task.assigned_to == m.id).count()
        m_completed = db.query(Task).filter(Task.assigned_to == m.id, Task.status == TaskStatus.COMPLETED.value).count()
        m_progress = int(round((m_completed / m_total) * 100)) if m_total > 0 else 0
        
        # Get assigned role if member of any project
        pm = db.query(ProjectMember).filter(ProjectMember.user_id == m.id).first()
        assigned_role = pm.assigned_role if pm else "Member"

        member_progress_list.append(
            MemberProgressItem(
                user_id=m.id,
                user_name=m.name,
                user_email=m.email,
                assigned_role=assigned_role,
                total_tasks=m_total,
                completed_tasks=m_completed,
                progress_percentage=m_progress,
            )
        )

    # Recent activity
    recent_activity_logs = db.query(ActivityLog).order_by(ActivityLog.created_at.desc()).limit(10).all()
    recent_activity = [ActivityLogOut.model_validate(log) for log in recent_activity_logs]

    # Recently completed tasks
    recently_completed_objs = (
        db.query(Task)
        .filter(Task.status == TaskStatus.COMPLETED.value)
        .order_by(Task.completed_at.desc().nullslast(), Task.updated_at.desc())
        .limit(5)
        .all()
    )
    recently_completed = []
    for t in recently_completed_objs:
        t_dict = TaskOut.model_validate(t)
        t_dict.is_overdue = False
        if t.project:
            t_dict.project_name = t.project.name
        recently_completed.append(t_dict)

    # Upcoming deadlines (due in future, not completed)
    now = datetime.now(timezone.utc)
    upcoming_objs = (
        db.query(Task)
        .filter(
            Task.status != TaskStatus.COMPLETED.value,
            Task.due_date.isnot(None),
        )
        .order_by(Task.due_date.asc())
        .limit(5)
        .all()
    )
    upcoming_deadlines = []
    for t in upcoming_objs:
        if not is_task_overdue(t):
            t_dict = TaskOut.model_validate(t)
            t_dict.is_overdue = False
            if t.project:
                t_dict.project_name = t.project.name
            upcoming_deadlines.append(t_dict)

    overdue_tasks_out = []
    for t in overdue_tasks_list[:5]:
        t_dict = TaskOut.model_validate(t)
        t_dict.is_overdue = True
        if t.project:
            t_dict.project_name = t.project.name
        overdue_tasks_out.append(t_dict)

    return LeadDashboardOut(
        total_team_members=total_members,
        total_tasks=total_tasks,
        completed_tasks=completed_tasks,
        in_progress_tasks=in_progress_tasks,
        pending_tasks=pending_tasks,
        overdue_tasks=overdue_count,
        overall_project_progress=overall_progress,
        team_member_progress=member_progress_list,
        recent_activity=recent_activity,
        recently_completed_tasks=recently_completed,
        upcoming_deadlines=upcoming_deadlines,
        overdue_tasks_list=overdue_tasks_out,
    )


@router.get("/member-dashboard", response_model=MemberDashboardOut)
def get_member_dashboard(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    assigned_total = db.query(Task).filter(Task.assigned_to == current_user.id).count()
    completed_count = db.query(Task).filter(
        Task.assigned_to == current_user.id, Task.status == TaskStatus.COMPLETED.value
    ).count()
    in_progress_count = db.query(Task).filter(
        Task.assigned_to == current_user.id, Task.status == TaskStatus.IN_PROGRESS.value
    ).count()
    pending_count = assigned_total - completed_count

    personal_progress = int(round((completed_count / assigned_total) * 100)) if assigned_total > 0 else 0

    # Today's tasks (due today or status IN_PROGRESS)
    assigned_tasks = db.query(Task).filter(Task.assigned_to == current_user.id).all()
    todays_tasks_objs = [t for t in assigned_tasks if t.status != TaskStatus.COMPLETED.value][:5]
    todays_tasks = []
    for t in todays_tasks_objs:
        t_dict = TaskOut.model_validate(t)
        t_dict.is_overdue = is_task_overdue(t)
        if t.project:
            t_dict.project_name = t.project.name
        todays_tasks.append(t_dict)

    # Upcoming deadlines
    upcoming_objs = (
        db.query(Task)
        .filter(
            Task.assigned_to == current_user.id,
            Task.status != TaskStatus.COMPLETED.value,
            Task.due_date.isnot(None),
        )
        .order_by(Task.due_date.asc())
        .limit(5)
        .all()
    )
    upcoming_deadlines = []
    for t in upcoming_objs:
        t_dict = TaskOut.model_validate(t)
        t_dict.is_overdue = is_task_overdue(t)
        if t.project:
            t_dict.project_name = t.project.name
        upcoming_deadlines.append(t_dict)

    # Activity logs involving current user
    logs = (
        db.query(ActivityLog)
        .filter(ActivityLog.user_id == current_user.id)
        .order_by(ActivityLog.created_at.desc())
        .limit(10)
        .all()
    )
    recent_activity = [ActivityLogOut.model_validate(l) for l in logs]

    # Unread notifications count
    unread_notifs = db.query(Notification).filter(
        Notification.user_id == current_user.id,
        Notification.is_read == False
    ).count()

    return MemberDashboardOut(
        welcome_message=f"Welcome back, {current_user.name}!",
        assigned_tasks_count=assigned_total,
        completed_tasks_count=completed_count,
        pending_tasks_count=pending_count,
        in_progress_tasks_count=in_progress_count,
        personal_progress=personal_progress,
        todays_tasks=todays_tasks,
        upcoming_deadlines=upcoming_deadlines,
        recent_activity=recent_activity,
        unread_notifications_count=unread_notifs,
    )


@router.get("/metrics", response_model=AnalyticsOut)
def get_analytics_metrics(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    total_tasks = db.query(Task).count()
    if total_tasks == 0:
        return AnalyticsOut(
            has_data=False,
            overall_progress=0,
            completed_vs_pending={"completed": 0, "pending": 0},
            tasks_by_status={"TODO": 0, "IN_PROGRESS": 0, "REVIEW": 0, "COMPLETED": 0},
            tasks_by_priority={"LOW": 0, "MEDIUM": 0, "HIGH": 0},
            member_task_distribution=[],
            overdue_count=0,
        )

    completed_count = db.query(Task).filter(Task.status == TaskStatus.COMPLETED.value).count()
    pending_count = total_tasks - completed_count
    overall_progress = int(round((completed_count / total_tasks) * 100))

    # Tasks by status
    tasks_by_status = {
        "TODO": db.query(Task).filter(Task.status == TaskStatus.TODO.value).count(),
        "IN_PROGRESS": db.query(Task).filter(Task.status == TaskStatus.IN_PROGRESS.value).count(),
        "REVIEW": db.query(Task).filter(Task.status == TaskStatus.REVIEW.value).count(),
        "COMPLETED": completed_count,
    }

    # Tasks by priority
    tasks_by_priority = {
        "LOW": db.query(Task).filter(Task.priority == TaskPriority.LOW.value).count(),
        "MEDIUM": db.query(Task).filter(Task.priority == TaskPriority.MEDIUM.value).count(),
        "HIGH": db.query(Task).filter(Task.priority == TaskPriority.HIGH.value).count(),
    }

    # Member task distribution
    members = db.query(User).filter(User.role == UserRole.TEAM_MEMBER.value).all()
    dist = []
    for m in members:
        count = db.query(Task).filter(Task.assigned_to == m.id).count()
        dist.append({"name": m.name, "task_count": count})

    # Overdue count
    all_tasks = db.query(Task).all()
    overdue_count = len([t for t in all_tasks if is_task_overdue(t)])

    return AnalyticsOut(
        has_data=True,
        overall_progress=overall_progress,
        completed_vs_pending={"completed": completed_count, "pending": pending_count},
        tasks_by_status=tasks_by_status,
        tasks_by_priority=tasks_by_priority,
        member_task_distribution=dist,
        overdue_count=overdue_count,
    )
