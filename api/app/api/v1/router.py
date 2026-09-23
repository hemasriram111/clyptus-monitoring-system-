from fastapi import APIRouter
from app.api.v1.auth import router as auth_router
from app.api.v1.users import router as users_router
from app.api.v1.projects import router as projects_router
from app.api.v1.tasks import router as tasks_router
from app.api.v1.groups import router as groups_router
from app.api.v1.messages import router as messages_router
from app.api.v1.notifications import router as notifications_router
from app.api.v1.activity import router as activity_router
from app.api.v1.analytics import router as analytics_router
from app.api.v1.calendar import router as calendar_router
from app.api.v1.attendance import router as attendance_router

api_v1_router = APIRouter(prefix="/api/v1")

api_v1_router.include_router(auth_router)
api_v1_router.include_router(users_router)
api_v1_router.include_router(projects_router)
api_v1_router.include_router(tasks_router)
api_v1_router.include_router(groups_router)
api_v1_router.include_router(messages_router)
api_v1_router.include_router(notifications_router)
api_v1_router.include_router(activity_router)
api_v1_router.include_router(analytics_router)
api_v1_router.include_router(calendar_router)
api_v1_router.include_router(attendance_router)

