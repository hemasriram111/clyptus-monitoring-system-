import os
import uuid
from typing import List, Optional
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status, Query, UploadFile, File
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.models.all_models import Task, User, UserRole, Project, TaskStatus, TaskPriority, TaskAttachment
from app.schemas.task import TaskCreate, TaskUpdate, TaskOut, TaskCommentCreate, TaskCommentOut, TaskAttachmentOut
from app.services.auth_service import get_current_user, get_current_team_lead
from app.services.task_service import (
    create_task,
    update_task,
    update_task_status,
    add_task_comment,
    is_task_overdue,
    add_task_attachment,
    get_task_attachments,
    delete_task_attachment,
)

router = APIRouter(prefix="/tasks", tags=["Tasks"])

UPLOAD_DIR = os.path.join(os.getcwd(), "uploads", "attachments")
os.makedirs(UPLOAD_DIR, exist_ok=True)


@router.get("", response_model=List[TaskOut])
def list_tasks(
    search: Optional[str] = Query(None, description="Search by title or description"),
    project_id: Optional[int] = Query(None, description="Filter by project"),
    assigned_to: Optional[int] = Query(None, description="Filter by assigned user"),
    status_filter: Optional[str] = Query(None, alias="status", description="Filter by status"),
    priority_filter: Optional[str] = Query(None, alias="priority", description="Filter by priority"),
    mine_only: bool = Query(False, description="Filter tasks assigned to current user"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = db.query(Task)

    if mine_only or current_user.role == UserRole.TEAM_MEMBER.value:
        q = q.filter(Task.assigned_to == current_user.id)

    if search:
        s = f"%{search}%"
        q = q.filter((Task.title.ilike(s)) | (Task.description.ilike(s)))

    if project_id:
        q = q.filter(Task.project_id == project_id)

    if assigned_to and not mine_only:
        q = q.filter(Task.assigned_to == assigned_to)

    if status_filter:
        q = q.filter(Task.status == status_filter)

    if priority_filter:
        q = q.filter(Task.priority == priority_filter)

    tasks = q.order_by(Task.created_at.desc()).all()

    res = []
    for t in tasks:
        t_dict = TaskOut.model_validate(t)
        t_dict.is_overdue = is_task_overdue(t)
        if t.project:
            t_dict.project_name = t.project.name
        res.append(t_dict)
    return res


@router.post("", response_model=TaskOut, status_code=status.HTTP_201_CREATED)
def create_new_task(
    task_in: TaskCreate,
    db: Session = Depends(get_db),
    current_lead: User = Depends(get_current_team_lead),
):
    project = db.query(Project).filter(Project.id == task_in.project_id).first()
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    if task_in.assigned_to:
        assignee = db.query(User).filter(User.id == task_in.assigned_to).first()
        if not assignee:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assigned user not found")

    task = create_task(db=db, task_in=task_in, creator_id=current_lead.id)
    t_dict = TaskOut.model_validate(task)
    t_dict.is_overdue = is_task_overdue(task)
    if task.project:
        t_dict.project_name = task.project.name
    return t_dict


@router.get("/{task_id}", response_model=TaskOut)
def get_task_by_id(
    task_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")

    t_dict = TaskOut.model_validate(task)
    t_dict.is_overdue = is_task_overdue(task)
    if task.project:
        t_dict.project_name = task.project.name
    return t_dict


@router.put("/{task_id}", response_model=TaskOut)
def update_task_details(
    task_id: int,
    task_in: TaskUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")

    # Team members can only update tasks assigned to them
    if current_user.role == UserRole.TEAM_MEMBER.value and task.assigned_to != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permission denied")

    updated = update_task(db=db, task_id=task_id, task_in=task_in, current_user=current_user)
    t_dict = TaskOut.model_validate(updated)
    t_dict.is_overdue = is_task_overdue(updated)
    if updated.project:
        t_dict.project_name = updated.project.name
    return t_dict


@router.patch("/{task_id}/status", response_model=TaskOut)
def change_task_status(
    task_id: int,
    status_str: str = Query(..., alias="status"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")

    if current_user.role == UserRole.TEAM_MEMBER.value and task.assigned_to != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permission denied")

    valid_statuses = [s.value for s in TaskStatus]
    if status_str not in valid_statuses:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid status. Must be one of {valid_statuses}")

    updated = update_task_status(db=db, task=task, new_status=status_str, current_user=current_user)
    t_dict = TaskOut.model_validate(updated)
    t_dict.is_overdue = is_task_overdue(updated)
    if updated.project:
        t_dict.project_name = updated.project.name
    return t_dict


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_task_by_id(
    task_id: int,
    db: Session = Depends(get_db),
    current_lead: User = Depends(get_current_team_lead),
):
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")

    db.delete(task)
    db.commit()
    return None


@router.post("/{task_id}/comments", response_model=TaskCommentOut, status_code=status.HTTP_201_CREATED)
def create_comment_on_task(
    task_id: int,
    comment_in: TaskCommentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")

    comment = add_task_comment(db=db, task_id=task_id, comment_in=comment_in, user=current_user)
    return comment


@router.post("/{task_id}/attachments", response_model=TaskAttachmentOut, status_code=status.HTTP_201_CREATED)
async def upload_attachment(
    task_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")

    # Member can only upload if assigned or lead
    if current_user.role == UserRole.TEAM_MEMBER.value and task.assigned_to != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permission denied")

    # Generate safe unique filename
    ext = os.path.splitext(file.filename)[1] if file.filename else ""
    unique_filename = f"{uuid.uuid4().hex}{ext}"
    file_path = os.path.join(UPLOAD_DIR, unique_filename)

    # Save file contents
    contents = await file.read()
    file_size = len(contents)
    with open(file_path, "wb") as f:
        f.write(contents)

    attachment = add_task_attachment(
        db=db,
        task_id=task_id,
        user=current_user,
        file_name=file.filename or "attachment",
        file_path=file_path,
        file_size=file_size,
    )
    return attachment


@router.get("/{task_id}/attachments", response_model=List[TaskAttachmentOut])
def list_task_attachments(
    task_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")

    return get_task_attachments(db=db, task_id=task_id)


@router.get("/attachments/{attachment_id}/download")
def download_attachment(
    attachment_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    att = db.query(TaskAttachment).filter(TaskAttachment.id == attachment_id).first()
    if not att or not os.path.exists(att.file_path):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Attachment file not found")

    return FileResponse(
        path=att.file_path,
        filename=att.file_name,
        media_type="application/octet-stream",
    )


@router.delete("/attachments/{attachment_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_attachment(
    attachment_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    success = delete_task_attachment(db=db, attachment_id=attachment_id, current_user=current_user)
    if not success:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Could not delete attachment")
    return None
