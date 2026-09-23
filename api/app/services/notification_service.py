from sqlalchemy.orm import Session
from app.models.all_models import Notification, NotificationType


def create_notification(
    db: Session,
    user_id: int,
    notification_type: str,
    title: str,
    message: str
) -> Notification:
    notif = Notification(
        user_id=user_id,
        type=notification_type,
        title=title,
        message=message,
        is_read=False
    )
    db.add(notif)
    db.commit()
    db.refresh(notif)
    return notif
