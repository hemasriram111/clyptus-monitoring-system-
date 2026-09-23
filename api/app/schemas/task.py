from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, ConfigDict
from app.models.all_models import TaskStatus, TaskPriority
from app.schemas.user import UserOut


class TaskCommentBase(BaseModel):
    comment: str


class TaskCommentCreate(TaskCommentBase):
    pass


class TaskCommentOut(TaskCommentBase):
    id: int
    task_id: int
    user_id: int
    created_at: datetime
    updated_at: datetime
    user: Optional[UserOut] = None

    model_config = ConfigDict(from_attributes=True)


class TaskAttachmentOut(BaseModel):
    id: int
    task_id: int
    user_id: int
    file_name: str
    file_path: str
    file_size: int
    created_at: datetime
    user: Optional[UserOut] = None

    model_config = ConfigDict(from_attributes=True)


class TaskBase(BaseModel):
    title: str
    description: Optional[str] = None
    priority: TaskPriority = TaskPriority.MEDIUM
    status: TaskStatus = TaskStatus.TODO
    due_date: Optional[datetime] = None
    estimated_hours: float = 0.0


class TaskCreate(TaskBase):
    project_id: int
    assigned_to: Optional[int] = None


class TaskUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    assigned_to: Optional[int] = None
    priority: Optional[TaskPriority] = None
    status: Optional[TaskStatus] = None
    due_date: Optional[datetime] = None
    estimated_hours: Optional[float] = None


class TaskOut(TaskBase):
    id: int
    project_id: int
    assigned_to: Optional[int] = None
    created_by: int
    created_at: datetime
    updated_at: datetime
    completed_at: Optional[datetime] = None
    is_overdue: bool = False
    assignee: Optional[UserOut] = None
    creator: Optional[UserOut] = None
    project_name: Optional[str] = None
    comments: List[TaskCommentOut] = []
    attachments: List[TaskAttachmentOut] = []

    model_config = ConfigDict(from_attributes=True)
