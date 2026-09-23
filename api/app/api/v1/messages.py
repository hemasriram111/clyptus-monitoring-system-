from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.core.database import get_db
from app.models.all_models import Message, GroupMessage, User, Group
from app.schemas.message import (
    MessageCreate,
    MessageOut,
    GroupMessageCreate,
    GroupMessageOut,
    UnreadCountOut,
)
from app.services.auth_service import get_current_user
from app.services.chat_service import (
    send_direct_message,
    get_direct_messages,
    send_group_message,
    get_group_messages,
)

router = APIRouter(prefix="/messages", tags=["Messaging"])


@router.get("/unread/count", response_model=UnreadCountOut)
def get_unread_messages_count(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    total_unread = db.query(Message).filter(
        Message.receiver_id == current_user.id,
        Message.is_read == False,
    ).count()

    sender_counts = (
        db.query(Message.sender_id, func.count(Message.id))
        .filter(
            Message.receiver_id == current_user.id,
            Message.is_read == False,
        )
        .group_by(Message.sender_id)
        .all()
    )
    by_sender = {str(sender_id): count for sender_id, count in sender_counts}

    return {
        "unread_count": total_unread,
        "unread_by_sender": by_sender,
    }


@router.post("/read-all")
def mark_all_messages_read(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    updated = db.query(Message).filter(
        Message.receiver_id == current_user.id,
        Message.is_read == False,
    ).update({"is_read": True})
    db.commit()
    return {"status": "success", "marked_read_count": updated}


@router.get("/{other_user_id}", response_model=List[MessageOut])
def get_user_messages(
    other_user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    other_user = db.query(User).filter(User.id == other_user_id).first()
    if not other_user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    messages = get_direct_messages(db=db, user1_id=current_user.id, user2_id=other_user_id)
    return messages


@router.post("", response_model=MessageOut, status_code=status.HTTP_201_CREATED)
def send_message_to_user(
    message_in: MessageCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if message_in.receiver_id == current_user.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot message yourself")

    receiver = db.query(User).filter(User.id == message_in.receiver_id).first()
    if not receiver:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Receiver user not found")

    msg = send_direct_message(db=db, sender_id=current_user.id, message_in=message_in)
    return msg


@router.patch("/{message_id}/read", response_model=MessageOut)
def mark_message_as_read(
    message_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    msg = db.query(Message).filter(Message.id == message_id).first()
    if not msg:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Message not found")

    if msg.receiver_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permission denied")

    msg.is_read = True
    db.commit()
    db.refresh(msg)
    return msg


@router.get("/groups/{group_id}", response_model=List[GroupMessageOut])
def get_messages_for_group(
    group_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    group = db.query(Group).filter(Group.id == group_id).first()
    if not group:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Group not found")

    messages = get_group_messages(db=db, group_id=group_id)
    return messages


@router.post("/groups", response_model=GroupMessageOut, status_code=status.HTTP_201_CREATED)
def post_group_message(
    message_in: GroupMessageCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    group = db.query(Group).filter(Group.id == message_in.group_id).first()
    if not group:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Group not found")

    msg = send_group_message(db=db, sender_id=current_user.id, message_in=message_in)
    return msg
