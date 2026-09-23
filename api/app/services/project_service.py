from typing import List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.models.all_models import Project, ProjectMember, Task, TaskStatus, User
from app.schemas.project import ProjectCreate, ProjectUpdate
from app.services.activity_service import log_activity


def calculate_project_progress(db: Session, project_id: int) -> tuple[int, int, int]:
    total_tasks = db.query(Task).filter(Task.project_id == project_id).count()
    completed_tasks = db.query(Task).filter(
        Task.project_id == project_id,
        Task.status == TaskStatus.COMPLETED.value
    ).count()

    if total_tasks == 0:
        progress = 0
    else:
        progress = int(round((completed_tasks / total_tasks) * 100))

    return total_tasks, completed_tasks, progress


def create_project(db: Session, project_in: ProjectCreate, team_lead_id: int) -> Project:
    db_project = Project(
        name=project_in.name,
        description=project_in.description,
        team_lead_id=team_lead_id,
        start_date=project_in.start_date,
        end_date=project_in.end_date,
        status="ACTIVE"
    )
    db.add(db_project)
    db.commit()
    db.refresh(db_project)

    # Automatically add team lead as project member
    member = ProjectMember(
        project_id=db_project.id,
        user_id=team_lead_id,
        assigned_role="Team Lead"
    )
    db.add(member)
    db.commit()

    # Log activity
    log_activity(
        db=db,
        user_id=team_lead_id,
        action=f"Created project '{db_project.name}'",
        entity_type="PROJECT",
        project_id=db_project.id,
        entity_id=db_project.id
    )

    return db_project


def update_project(db: Session, project_id: int, project_in: ProjectUpdate, user_id: int) -> Optional[Project]:
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        return None

    update_data = project_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(project, field, value)

    db.commit()
    db.refresh(project)

    log_activity(
        db=db,
        user_id=user_id,
        action=f"Updated project '{project.name}'",
        entity_type="PROJECT",
        project_id=project.id,
        entity_id=project.id
    )

    return project
