from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.models.all_models import User, UserRole, ProjectMember, Project
from app.schemas.user import UserOut, UserCreate, UserUpdate
from app.services.auth_service import get_current_user, get_current_team_lead
from app.services.user_service import create_user_by_lead, get_users_list, toggle_user_active_status
from app.services.activity_service import log_activity

router = APIRouter(prefix="/users", tags=["Users & Team Members"])


@router.get("", response_model=List[UserOut])
def list_users(
    query: Optional[str] = Query(None, description="Search by name or email"),
    role: Optional[str] = Query(None, description="Filter by role"),
    project_id: Optional[int] = Query(None, description="Filter by project membership"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    users = get_users_list(db=db, query_str=query, role=role, project_id=project_id)
    result = []
    for u in users:
        u_dict = UserOut.model_validate(u)
        if project_id:
            pm = db.query(ProjectMember).filter(ProjectMember.project_id == project_id, ProjectMember.user_id == u.id).first()
            if pm:
                u_dict.assigned_role = pm.assigned_role
        result.append(u_dict)
    return result


@router.post("", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def create_member(
    user_in: UserCreate,
    db: Session = Depends(get_db),
    current_lead: User = Depends(get_current_team_lead),
):
    try:
        user = create_user_by_lead(db=db, user_in=user_in, lead_id=current_lead.id)
        return user
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/{user_id}", response_model=UserOut)
def get_user_detail(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user


@router.put("/{user_id}", response_model=UserOut)
def update_user(
    user_id: int,
    user_in: UserUpdate,
    db: Session = Depends(get_db),
    current_lead: User = Depends(get_current_team_lead),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    update_data = user_in.model_dump(exclude_unset=True)

    if "role" in update_data and update_data["role"]:
        val = update_data["role"]
        update_data["role"] = val.value if hasattr(val, 'value') else str(val)

    project_role = update_data.pop("project_role", None)

    for field, val in update_data.items():
        if val is not None:
            setattr(user, field, val)

    db.commit()
    db.refresh(user)

    log_activity(
        db=db,
        user_id=current_lead.id,
        action=f"Updated user details for '{user.name}'",
        entity_type="USER",
        entity_id=user.id,
    )

    return user


@router.patch("/{user_id}/toggle-active", response_model=UserOut)
def toggle_active(
    user_id: int,
    db: Session = Depends(get_db),
    current_lead: User = Depends(get_current_team_lead),
):
    if user_id == current_lead.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot deactivate yourself.")
    try:
        user = toggle_user_active_status(db=db, user_id=user_id, lead_id=current_lead.id)
        return user
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
