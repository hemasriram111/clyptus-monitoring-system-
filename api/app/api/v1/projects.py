from datetime import datetime, timezone
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.models.all_models import Project, ProjectMember, User, Task, TaskStatus
from app.schemas.project import ProjectCreate, ProjectUpdate, ProjectOut, ProjectMemberAdd, ProjectMemberOut
from app.services.auth_service import get_current_user, get_current_team_lead
from app.services.project_service import create_project, update_project, calculate_project_progress
from app.services.activity_service import log_activity

router = APIRouter(prefix="/projects", tags=["Projects"])


def _normalize_datetime(value: Optional[datetime]) -> datetime:
    if value is None:
        return datetime.min.replace(tzinfo=timezone.utc)
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _project_sort_key(project: Project):
    start = _normalize_datetime(project.start_date)
    end = _normalize_datetime(project.end_date)
    return (start, end, project.id)


@router.get("", response_model=List[ProjectOut])
def list_projects(
    sort: str = Query("earliest", description="Date sort for the project range: earliest, latest, asc, or desc."),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    sort_key = (sort or "earliest").lower()
    if sort_key in {"asc", "earliest", "from_date", "from-date", "start_date", "start-date"}:
        sort_key = "earliest"
    elif sort_key in {"desc", "dsc", "latest", "to_date", "to-date", "end_date", "end-date"}:
        sort_key = "latest"

    if current_user.role == "TEAM_LEAD":
        projects = db.query(Project).all()
    else:
        # Team Members see projects they are assigned to
        projects = (
            db.query(Project)
            .join(ProjectMember, ProjectMember.project_id == Project.id)
            .filter(ProjectMember.user_id == current_user.id)
            .all()
        )

    sort_reverse = sort_key == "latest"
    projects = sorted(projects, key=_project_sort_key, reverse=sort_reverse)

    res = []
    for p in projects:
        total_tasks, completed_tasks, progress = calculate_project_progress(db, p.id)
        p_dict = ProjectOut.model_validate(p)
        p_dict.task_count = total_tasks
        p_dict.completed_task_count = completed_tasks
        p_dict.progress_percentage = progress
        res.append(p_dict)
    return res


@router.post("", response_model=ProjectOut, status_code=status.HTTP_201_CREATED)
def create_new_project(
    project_in: ProjectCreate,
    db: Session = Depends(get_db),
    current_lead: User = Depends(get_current_team_lead),
):
    project = create_project(db=db, project_in=project_in, team_lead_id=current_lead.id)
    total_tasks, completed_tasks, progress = calculate_project_progress(db, project.id)
    p_dict = ProjectOut.model_validate(project)
    p_dict.task_count = total_tasks
    p_dict.completed_task_count = completed_tasks
    p_dict.progress_percentage = progress
    return p_dict


@router.get("/{project_id}", response_model=ProjectOut)
def get_project_by_id(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    total_tasks, completed_tasks, progress = calculate_project_progress(db, project.id)
    p_dict = ProjectOut.model_validate(project)
    p_dict.task_count = total_tasks
    p_dict.completed_task_count = completed_tasks
    p_dict.progress_percentage = progress
    return p_dict


@router.put("/{project_id}", response_model=ProjectOut)
def edit_project(
    project_id: int,
    project_in: ProjectUpdate,
    db: Session = Depends(get_db),
    current_lead: User = Depends(get_current_team_lead),
):
    project = update_project(db=db, project_id=project_id, project_in=project_in, user_id=current_lead.id)
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    total_tasks, completed_tasks, progress = calculate_project_progress(db, project.id)
    p_dict = ProjectOut.model_validate(project)
    p_dict.task_count = total_tasks
    p_dict.completed_task_count = completed_tasks
    p_dict.progress_percentage = progress
    return p_dict


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(
    project_id: int,
    db: Session = Depends(get_db),
    current_lead: User = Depends(get_current_team_lead),
):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    db.delete(project)
    db.commit()
    return None


@router.post("/{project_id}/members", response_model=ProjectMemberOut, status_code=status.HTTP_201_CREATED)
def add_project_member(
    project_id: int,
    member_in: ProjectMemberAdd,
    db: Session = Depends(get_db),
    current_lead: User = Depends(get_current_team_lead),
):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    user = db.query(User).filter(User.id == member_in.user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    existing = db.query(ProjectMember).filter(
        ProjectMember.project_id == project_id,
        ProjectMember.user_id == member_in.user_id
    ).first()
    if existing:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User is already a member of this project.")

    pm = ProjectMember(
        project_id=project_id,
        user_id=member_in.user_id,
        assigned_role=member_in.assigned_role or "Member"
    )
    db.add(pm)
    db.commit()
    db.refresh(pm)

    log_activity(
        db=db,
        user_id=current_lead.id,
        action=f"Added '{user.name}' to project '{project.name}'",
        entity_type="PROJECT_MEMBER",
        project_id=project.id,
        entity_id=pm.id,
    )

    return pm


@router.delete("/{project_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_project_member(
    project_id: int,
    user_id: int,
    db: Session = Depends(get_db),
    current_lead: User = Depends(get_current_team_lead),
):
    pm = db.query(ProjectMember).filter(
        ProjectMember.project_id == project_id,
        ProjectMember.user_id == user_id
    ).first()
    if not pm:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project member not found.")

    db.delete(pm)
    db.commit()

    log_activity(
        db=db,
        user_id=current_lead.id,
        action=f"Removed user #{user_id} from project #{project_id}",
        entity_type="PROJECT_MEMBER",
        project_id=project_id,
    )
    return None
