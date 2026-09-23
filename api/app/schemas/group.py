from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, ConfigDict
from app.schemas.user import UserOut


class GroupMemberAdd(BaseModel):
    user_id: int


class GroupMemberOut(BaseModel):
    id: int
    group_id: int
    user_id: int
    joined_at: datetime
    user: Optional[UserOut] = None

    model_config = ConfigDict(from_attributes=True)


class GroupBase(BaseModel):
    name: str
    description: Optional[str] = None
    project_id: Optional[int] = None


class GroupCreate(GroupBase):
    member_ids: Optional[List[int]] = []


class GroupOut(GroupBase):
    id: int
    created_by: int
    created_at: datetime
    members: List[GroupMemberOut] = []
    member_count: int = 0

    model_config = ConfigDict(from_attributes=True)
