from datetime import datetime, timezone
from typing import Optional, Dict
from pydantic import BaseModel, ConfigDict, field_serializer
from app.schemas.user import UserOut


class UnreadCountOut(BaseModel):
    unread_count: int
    unread_by_sender: Dict[str, int] = {}


class MessageCreate(BaseModel):
    receiver_id: int
    message: str


class MessageOut(BaseModel):
    id: int
    sender_id: int
    receiver_id: int
    message: str
    is_read: bool
    created_at: datetime
    sender: Optional[UserOut] = None
    receiver: Optional[UserOut] = None

    model_config = ConfigDict(from_attributes=True)

    @field_serializer("created_at")
    def serialize_created_at(self, dt: datetime, _info):
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.isoformat()


class GroupMessageCreate(BaseModel):
    group_id: int
    message: str


class GroupMessageOut(BaseModel):
    id: int
    group_id: int
    sender_id: int
    message: str
    created_at: datetime
    sender: Optional[UserOut] = None

    model_config = ConfigDict(from_attributes=True)

    @field_serializer("created_at")
    def serialize_created_at(self, dt: datetime, _info):
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.isoformat()

