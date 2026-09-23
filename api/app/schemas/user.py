from datetime import datetime
from typing import Optional
from pydantic import BaseModel, EmailStr, Field, ConfigDict
from app.models.all_models import UserRole


class UserBase(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    email: EmailStr
    role: UserRole = UserRole.TEAM_MEMBER
    profile_image: Optional[str] = None


class UserCreate(UserBase):
    password: str = Field(..., min_length=6)
    project_role: Optional[str] = "Member"
    project_id: Optional[int] = None


class UserRegister(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    email: EmailStr
    password: str = Field(..., min_length=6)
    role: UserRole = UserRole.TEAM_MEMBER


class UserUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[EmailStr] = None
    role: Optional[UserRole] = None
    profile_image: Optional[str] = None
    is_active: Optional[bool] = None
    project_role: Optional[str] = None


class UserOut(UserBase):
    id: int
    is_active: bool
    created_at: datetime
    updated_at: datetime
    assigned_role: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class TokenData(BaseModel):
    user_id: Optional[int] = None
    email: Optional[str] = None
    role: Optional[str] = None


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    email: EmailStr
    new_password: str = Field(..., min_length=6)

