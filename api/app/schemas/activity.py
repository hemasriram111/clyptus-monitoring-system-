from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict
from app.schemas.user import UserOut


class ActivityLogOut(BaseModel):
    id: int
    project_id: Optional[int] = None
    user_id: int
    action: str
    entity_type: str
    entity_id: Optional[int] = None
    created_at: datetime
    user: Optional[UserOut] = None

    model_config = ConfigDict(from_attributes=True)
