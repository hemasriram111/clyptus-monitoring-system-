from datetime import datetime, timezone
from typing import List, Optional
from sqlalchemy.orm import Session
from app.models.all_models import Task, TaskStatus, TaskComment, TaskAttachment, Project, User, NotificationType, UserRole
from app.schemas.task import TaskCreate, TaskUpdate, TaskCommentCreate
from app.services.activity_service import log_activity
from app.services.notification_service import create_notification


def is_task_overdue(task: Task) -> bool:
    if task.status == TaskStatus.COMPLETED.value or task.status == TaskStatus.COMPLETED:
        return False
    if task.due_date is None:
        return False
    # Compare UTC timestamps
    now = datetime.now(timezone.utc)
    due = task.due_date.replace(tzinfo=timezone.utc) if task.due_date.tzinfo is None else task.due_date
    return now > due


def create_task(db: Session, task_in: TaskCreate, creator_id: int) -> Task:
    task = Task(
        project_id=task_in.project_id,
        title=task_in.title,
        description=task_in.description,
        assigned_to=task_in.assigned_to,
        created_by=creator_id,
        priority=task_in.priority.value if hasattr(task_in.priority, 'value') else str(task_in.priority),
        status=task_in.status.value if hasattr(task_in.status, 'value') else str(task_in.status),
        due_date=task_in.due_date,
        estimated_hours=task_in.estimated_hours,
    )
    db.add(task)
    db.commit()
    db.refresh(task)

    # Activity log
    log_activity(
        db=db,
        user_id=creator_id,
        action=f"Created task '{task.title}'",
        entity_type="TASK",
        project_id=task.project_id,
        entity_id=task.id,
    )

    # Notification to assigned user if present
    if task.assigned_to and task.assigned_to != creator_id:
        create_notification(
            db=db,
            user_id=task.assigned_to,
            notification_type=NotificationType.TASK_ASSIGNED.value,
            title="New Task Assigned",
            message=f"You have been assigned to task: '{task.title}'"
        )

    return task


def update_task_status(db: Session, task: Task, new_status: str, current_user: User) -> Task:
    old_status = task.status
    task.status = new_status

    if new_status == TaskStatus.COMPLETED.value or new_status == TaskStatus.COMPLETED:
        task.completed_at = datetime.now(timezone.utc)
    else:
        task.completed_at = None

    db.commit()
    db.refresh(task)

    # Log activity
    action_text = f"Marked task '{task.title}' as {new_status}"
    log_activity(
        db=db,
        user_id=current_user.id,
        action=action_text,
        entity_type="TASK",
        project_id=task.project_id,
        entity_id=task.id,
    )

    # If completed by member, notify task creator / team lead
    if new_status == TaskStatus.COMPLETED.value or new_status == TaskStatus.COMPLETED:
        # Notify task creator if different from current user
        if task.created_by and task.created_by != current_user.id:
            create_notification(
                db=db,
                user_id=task.created_by,
                notification_type=NotificationType.TASK_COMPLETED.value,
                title="Task Completed",
                message=f"{current_user.name} completed the task: '{task.title}'"
            )

        # Also notify project team lead if different from creator and current user
        project = db.query(Project).filter(Project.id == task.project_id).first()
        if project and project.team_lead_id not in (current_user.id, task.created_by):
            create_notification(
                db=db,
                user_id=project.team_lead_id,
                notification_type=NotificationType.TASK_COMPLETED.value,
                title="Task Completed",
                message=f"{current_user.name} completed the task: '{task.title}' in {project.name}"
            )

    return task


def update_task(db: Session, task_id: int, task_in: TaskUpdate, current_user: User) -> Optional[Task]:
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        return None

    previous_assigned_to = task.assigned_to
    update_data = task_in.model_dump(exclude_unset=True)

    for field, value in update_data.items():
        if value is not None:
            if isinstance(value, (TaskStatus, TaskPriority)):
                value = value.value
            setattr(task, field, value)

    if task.status == TaskStatus.COMPLETED.value and not task.completed_at:
        task.completed_at = datetime.now(timezone.utc)
    elif task.status != TaskStatus.COMPLETED.value:
        task.completed_at = None

    db.commit()
    db.refresh(task)

    # Notify newly assigned user
    if task.assigned_to and task.assigned_to != previous_assigned_to and task.assigned_to != current_user.id:
        create_notification(
            db=db,
            user_id=task.assigned_to,
            notification_type=NotificationType.TASK_ASSIGNED.value,
            title="Task Assigned to You",
            message=f"You were assigned to task: '{task.title}'"
        )

    log_activity(
        db=db,
        user_id=current_user.id,
        action=f"Updated task '{task.title}'",
        entity_type="TASK",
        project_id=task.project_id,
        entity_id=task.id,
    )

    return task


def add_task_comment(db: Session, task_id: int, comment_in: TaskCommentCreate, user: User) -> TaskComment:
    comment = TaskComment(
        task_id=task_id,
        user_id=user.id,
        comment=comment_in.comment
    )
    db.add(comment)
    db.commit()
    db.refresh(comment)

    task = db.query(Task).filter(Task.id == task_id).first()
    if task:
        log_activity(
            db=db,
            user_id=user.id,
            action=f"Commented on task '{task.title}'",
            entity_type="TASK_COMMENT",
            project_id=task.project_id,
            entity_id=task.id,
        )

    return comment


def add_task_attachment(
    db: Session,
    task_id: int,
    user: User,
    file_name: str,
    file_path: str,
    file_size: int,
) -> TaskAttachment:
    attachment = TaskAttachment(
        task_id=task_id,
        user_id=user.id,
        file_name=file_name,
        file_path=file_path,
        file_size=file_size,
    )
    db.add(attachment)
    db.commit()
    db.refresh(attachment)

    task = db.query(Task).filter(Task.id == task_id).first()
    if task:
        log_activity(
            db=db,
            user_id=user.id,
            action=f"Uploaded attachment '{file_name}' to task '{task.title}'",
            entity_type="TASK_ATTACHMENT",
            project_id=task.project_id,
            entity_id=task.id,
        )

    return attachment


def get_task_attachments(db: Session, task_id: int) -> List[TaskAttachment]:
    return db.query(TaskAttachment).filter(TaskAttachment.task_id == task_id).order_by(TaskAttachment.created_at.desc()).all()


def delete_task_attachment(db: Session, attachment_id: int, current_user: User) -> bool:
    att = db.query(TaskAttachment).filter(TaskAttachment.id == attachment_id).first()
    if not att:
        return False

    # Lead can delete any; member can delete their own
    if current_user.role == UserRole.TEAM_MEMBER.value and att.user_id != current_user.id:
        return False

    task = db.query(Task).filter(Task.id == att.task_id).first()
    file_name = att.file_name
    project_id = task.project_id if task else None
    task_id = att.task_id

    db.delete(att)
    db.commit()

    if task:
        log_activity(
            db=db,
            user_id=current_user.id,
            action=f"Deleted attachment '{file_name}' from task '{task.title}'",
            entity_type="TASK_ATTACHMENT",
            project_id=project_id,
            entity_id=task_id,
        )

    return True
