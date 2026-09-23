from typing import List, Optional
from sqlalchemy.orm import Session
from app.models.all_models import User, ProjectMember, UserRole, Project
from app.schemas.user import UserCreate, UserUpdate
from app.core.security import hash_password
from app.services.activity_service import log_activity


def create_user_by_lead(db: Session, user_in: UserCreate, lead_id: int) -> User:
    # Check duplicate email
    existing = db.query(User).filter(User.email == user_in.email).first()
    if existing:
        raise ValueError(f"User with email '{user_in.email}' already exists.")

    hashed_pw = hash_password(user_in.password)
    role_val = user_in.role.value if hasattr(user_in.role, 'value') else str(user_in.role)

    user = User(
        name=user_in.name,
        email=user_in.email,
        password_hash=hashed_pw,
        role=role_val,
        profile_image=user_in.profile_image,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    # If project_id provided, add user to project
    if user_in.project_id:
        project = db.query(Project).filter(Project.id == user_in.project_id).first()
        if project:
            pm = ProjectMember(
                project_id=project.id,
                user_id=user.id,
                assigned_role=user_in.project_role or "Member"
            )
            db.add(pm)
            db.commit()

    log_activity(
        db=db,
        user_id=lead_id,
        action=f"Created user '{user.name}' ({user.role})",
        entity_type="USER",
        entity_id=user.id,
    )

    return user


def get_users_list(
    db: Session,
    query_str: Optional[str] = None,
    role: Optional[str] = None,
    project_id: Optional[int] = None
) -> List[User]:
    q = db.query(User)

    if query_str:
        search = f"%{query_str}%"
        q = q.filter((User.name.ilike(search)) | (User.email.ilike(search)))

    if role:
        q = q.filter(User.role == role)

    if project_id:
        q = q.join(ProjectMember, ProjectMember.user_id == User.id).filter(ProjectMember.project_id == project_id)

    return q.all()


def toggle_user_active_status(db: Session, user_id: int, lead_id: int) -> User:
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise ValueError("User not found")

    user.is_active = not user.is_active
    db.commit()
    db.refresh(user)

    status_str = "activated" if user.is_active else "deactivated"
    log_activity(
        db=db,
        user_id=lead_id,
        action=f"{status_str.capitalize()} user '{user.name}'",
        entity_type="USER",
        entity_id=user.id,
    )

    return user
