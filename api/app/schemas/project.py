from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, ConfigDict
from app.schemas.user import UserOut


class ProjectBase(BaseModel):
    name: str
    description: Optional[str] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None


class ProjectCreate(ProjectBase):
    pass


class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None


class ProjectMemberOut(BaseModel):
    id: int
    project_id: int
    user_id: int
    assigned_role: Optional[str] = "Member"
    joined_at: datetime
    user: Optional[UserOut] = None

    model_config = ConfigDict(from_attributes=True)


class ProjectMemberAdd(BaseModel):
    user_id: int
    assigned_role: Optional[str] = "Member"


class ProjectOut(ProjectBase):
    id: int
    team_lead_id: int
    status: str
    created_at: datetime
    updated_at: datetime
    team_lead: Optional[UserOut] = None
    members: List[ProjectMemberOut] = []
    task_count: int = 0
    completed_task_count: int = 0
    progress_percentage: int = 0

    model_config = ConfigDict(from_attributes=True)
