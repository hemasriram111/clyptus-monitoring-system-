from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.models.all_models import Group, GroupMember, User, UserRole
from app.schemas.group import GroupCreate, GroupOut, GroupMemberAdd, GroupMemberOut
from app.schemas.message import GroupMessageOut, GroupMessageCreate
from app.services.auth_service import get_current_user, get_current_team_lead
from app.services.group_service import create_group, add_member_to_group, remove_member_from_group
from app.services.chat_service import get_group_messages, send_group_message
from pydantic import BaseModel

router = APIRouter(prefix="/groups", tags=["Groups"])


@router.get("", response_model=List[GroupOut])
def list_groups(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role == UserRole.TEAM_LEAD.value:
        groups = db.query(Group).all()
    else:
        # Team Members see groups they belong to
        groups = (
            db.query(Group)
            .join(GroupMember, GroupMember.group_id == Group.id)
            .filter(GroupMember.user_id == current_user.id)
            .all()
        )

    res = []
    for g in groups:
        g_dict = GroupOut.model_validate(g)
        g_dict.member_count = len(g.members)
        res.append(g_dict)
    return res


@router.post("", response_model=GroupOut, status_code=status.HTTP_201_CREATED)
def create_new_group(
    group_in: GroupCreate,
    db: Session = Depends(get_db),
    current_lead: User = Depends(get_current_team_lead),
):
    group = create_group(db=db, group_in=group_in, creator_id=current_lead.id)
    g_dict = GroupOut.model_validate(group)
    g_dict.member_count = len(group.members)
    return g_dict


@router.get("/{group_id}", response_model=GroupOut)
def get_group_by_id(
    group_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    group = db.query(Group).filter(Group.id == group_id).first()
    if not group:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Group not found")

    g_dict = GroupOut.model_validate(group)
    g_dict.member_count = len(group.members)
    return g_dict


@router.delete("/{group_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_group(
    group_id: int,
    db: Session = Depends(get_db),
    current_lead: User = Depends(get_current_team_lead),
):
    group = db.query(Group).filter(Group.id == group_id).first()
    if not group:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Group not found")

    db.delete(group)
    db.commit()
    return None


@router.post("/{group_id}/members", response_model=GroupMemberOut, status_code=status.HTTP_201_CREATED)
def add_member(
    group_id: int,
    member_in: GroupMemberAdd,
    db: Session = Depends(get_db),
    current_lead: User = Depends(get_current_team_lead),
):
    group = db.query(Group).filter(Group.id == group_id).first()
    if not group:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Group not found")

    user = db.query(User).filter(User.id == member_in.user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    gm = add_member_to_group(db=db, group_id=group_id, user_id=member_in.user_id, added_by_id=current_lead.id)
    return gm


@router.delete("/{group_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_member(
    group_id: int,
    user_id: int,
    db: Session = Depends(get_db),
    current_lead: User = Depends(get_current_team_lead),
):
    success = remove_member_from_group(db=db, group_id=group_id, user_id=user_id)
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Group member not found")
    return None


class SimpleMessageIn(BaseModel):
    message: str


@router.get("/{group_id}/messages", response_model=List[GroupMessageOut])
def list_group_messages_endpoint(
    group_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    group = db.query(Group).filter(Group.id == group_id).first()
    if not group:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Group not found")

    return get_group_messages(db=db, group_id=group_id)


@router.post("/{group_id}/messages", response_model=GroupMessageOut, status_code=status.HTTP_201_CREATED)
def send_group_message_endpoint(
    group_id: int,
    msg_in: SimpleMessageIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    group = db.query(Group).filter(Group.id == group_id).first()
    if not group:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Group not found")

    full_msg_in = GroupMessageCreate(group_id=group_id, message=msg_in.message)
    return send_group_message(db=db, sender_id=current_user.id, message_in=full_msg_in)

