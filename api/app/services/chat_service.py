from datetime import datetime, timezone
from typing import List
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_
from app.models.all_models import Message, GroupMessage, Group, GroupMember, User, NotificationType
from app.schemas.message import MessageCreate, GroupMessageCreate
from app.services.notification_service import create_notification


def send_direct_message(db: Session, sender_id: int, message_in: MessageCreate) -> Message:
    msg = Message(
        sender_id=sender_id,
        receiver_id=message_in.receiver_id,
        message=message_in.message,
        created_at=datetime.now(timezone.utc),
        is_read=False,
    )
    db.add(msg)
    db.commit()
    db.refresh(msg)

    # Send notification
    sender = db.query(User).filter(User.id == sender_id).first()
    sender_name = sender.name if sender else "Someone"
    create_notification(
        db=db,
        user_id=message_in.receiver_id,
        notification_type=NotificationType.NEW_MESSAGE.value,
        title="New Message",
        message=f"{sender_name}: {message_in.message[:50]}..." if len(message_in.message) > 50 else f"{sender_name}: {message_in.message}"
    )

    return msg


def get_direct_messages(db: Session, user1_id: int, user2_id: int) -> List[Message]:
    messages = db.query(Message).filter(
        or_(
            and_(Message.sender_id == user1_id, Message.receiver_id == user2_id),
            and_(Message.sender_id == user2_id, Message.receiver_id == user1_id)
        )
    ).order_by(Message.created_at.asc()).all()

    # Mark incoming messages as read
    db.query(Message).filter(
        Message.sender_id == user2_id,
        Message.receiver_id == user1_id,
        Message.is_read == False
    ).update({"is_read": True})
    db.commit()

    return messages


def send_group_message(db: Session, sender_id: int, message_in: GroupMessageCreate) -> GroupMessage:
    msg = GroupMessage(
        group_id=message_in.group_id,
        sender_id=sender_id,
        message=message_in.message,
        created_at=datetime.now(timezone.utc),
    )
    db.add(msg)
    db.commit()
    db.refresh(msg)
    return msg


def get_group_messages(db: Session, group_id: int) -> List[GroupMessage]:
    return db.query(GroupMessage).filter(GroupMessage.group_id == group_id).order_by(GroupMessage.created_at.asc()).all()
