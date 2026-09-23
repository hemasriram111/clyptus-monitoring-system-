from typing import List, Optional
from sqlalchemy.orm import Session
from app.models.all_models import Group, GroupMember, User, NotificationType
from app.schemas.group import GroupCreate
from app.services.activity_service import log_activity
from app.services.notification_service import create_notification


def create_group(db: Session, group_in: GroupCreate, creator_id: int) -> Group:
    group = Group(
        name=group_in.name,
        description=group_in.description,
        project_id=group_in.project_id,
        created_by=creator_id,
    )
    db.add(group)
    db.commit()
    db.refresh(group)

    # Always add creator to group
    members_to_add = set(group_in.member_ids or [])
    members_to_add.add(creator_id)

    for uid in members_to_add:
        gm = GroupMember(group_id=group.id, user_id=uid)
        db.add(gm)
        if uid != creator_id:
            create_notification(
                db=db,
                user_id=uid,
                notification_type=NotificationType.GROUP_ADDED.value,
                title="Added to Group",
                message=f"You were added to group '{group.name}'"
            )

    db.commit()

    log_activity(
        db=db,
        user_id=creator_id,
        action=f"Created group '{group.name}'",
        entity_type="GROUP",
        project_id=group.project_id,
        entity_id=group.id,
    )

    return group


def add_member_to_group(db: Session, group_id: int, user_id: int, added_by_id: int) -> GroupMember:
    existing = db.query(GroupMember).filter(
        GroupMember.group_id == group_id,
        GroupMember.user_id == user_id
    ).first()
    if existing:
        return existing

    gm = GroupMember(group_id=group_id, user_id=user_id)
    db.add(gm)
    db.commit()
    db.refresh(gm)

    group = db.query(Group).filter(Group.id == group_id).first()
    group_name = group.name if group else "a group"

    create_notification(
        db=db,
        user_id=user_id,
        notification_type=NotificationType.GROUP_ADDED.value,
        title="Added to Group",
        message=f"You were added to group '{group_name}'"
    )

    return gm


def remove_member_from_group(db: Session, group_id: int, user_id: int) -> bool:
    gm = db.query(GroupMember).filter(
        GroupMember.group_id == group_id,
        GroupMember.user_id == user_id
    ).first()
    if not gm:
        return False

    db.delete(gm)
    db.commit()
    return True
