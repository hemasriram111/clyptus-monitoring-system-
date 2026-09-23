from typing import List, Dict, Any, Optional
from pydantic import BaseModel
from app.schemas.task import TaskOut
from app.schemas.activity import ActivityLogOut
from app.schemas.user import UserOut


class MemberProgressItem(BaseModel):
    user_id: int
    user_name: str
    user_email: str
    assigned_role: Optional[str] = "Member"
    total_tasks: int
    completed_tasks: int
    progress_percentage: int


class LeadDashboardOut(BaseModel):
    total_team_members: int
    total_tasks: int
    completed_tasks: int
    in_progress_tasks: int
    pending_tasks: int  # TODO status
    overdue_tasks: int
    overall_project_progress: int
    team_member_progress: List[MemberProgressItem]
    recent_activity: List[ActivityLogOut]
    recently_completed_tasks: List[TaskOut]
    upcoming_deadlines: List[TaskOut]
    overdue_tasks_list: List[TaskOut]


class MemberDashboardOut(BaseModel):
    welcome_message: str
    assigned_tasks_count: int
    completed_tasks_count: int
    pending_tasks_count: int
    in_progress_tasks_count: int
    personal_progress: int
    todays_tasks: List[TaskOut]
    upcoming_deadlines: List[TaskOut]
    recent_activity: List[ActivityLogOut]
    unread_notifications_count: int


class CalendarEvent(BaseModel):
    id: str
    title: str
    type: str  # "TASK_DEADLINE", "PROJECT_START", "PROJECT_END"
    date: str
    status: Optional[str] = None
    priority: Optional[str] = None
    project_name: Optional[str] = None


class AnalyticsOut(BaseModel):
    has_data: bool
    overall_progress: int
    completed_vs_pending: Dict[str, int]
    tasks_by_status: Dict[str, int]
    tasks_by_priority: Dict[str, int]
    member_task_distribution: List[Dict[str, Any]]
    overdue_count: int
