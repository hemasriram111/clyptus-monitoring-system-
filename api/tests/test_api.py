import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.main import app
from app.core.database import Base, get_db

SQLALCHEMY_DATABASE_URL = "sqlite:///./test_project_monitoring.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db
client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


def test_register_and_login_lead():
    # Register Team Lead
    res = client.post(
        "/api/v1/auth/register",
        json={
            "name": "Alice Lead",
            "email": "alice@example.com",
            "password": "password123",
            "role": "TEAM_LEAD",
        },
    )
    assert res.status_code == 201
    data = res.json()
    assert "access_token" in data
    assert data["user"]["role"] == "TEAM_LEAD"

    # Login
    res_login = client.post(
        "/api/v1/auth/login",
        json={"email": "alice@example.com", "password": "password123"},
    )
    assert res_login.status_code == 200
    token = res_login.json()["access_token"]

    # Test /auth/me
    res_me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert res_me.status_code == 200
    assert res_me.json()["email"] == "alice@example.com"


def test_forgot_and_reset_password():
    client.post(
        "/api/v1/auth/register",
        json={
            "name": "Bob Member",
            "email": "bob@example.com",
            "password": "oldpassword123",
            "role": "TEAM_MEMBER",
        },
    )

    # Forgot Password lookup
    res = client.post("/api/v1/auth/forgot-password", json={"email": "bob@example.com"})
    assert res.status_code == 200
    assert res.json()["email"] == "bob@example.com"

    # Reset Password
    res = client.post(
        "/api/v1/auth/reset-password",
        json={"email": "bob@example.com", "new_password": "newpassword123"},
    )
    assert res.status_code == 200

    # Login with new password
    res = client.post(
        "/api/v1/auth/login",
        json={"email": "bob@example.com", "password": "newpassword123"},
    )
    assert res.status_code == 200
    assert "access_token" in res.json()



def test_full_project_and_task_lifecycle():
    # 1. Register Team Lead
    res_lead = client.post(
        "/api/v1/auth/register",
        json={
            "name": "Lead Boss",
            "email": "boss@example.com",
            "password": "password123",
            "role": "TEAM_LEAD",
        },
    )
    lead_token = res_lead.json()["access_token"]
    headers_lead = {"Authorization": f"Bearer {lead_token}"}

    # 2. Check Lead Dashboard on empty DB
    res_dash_empty = client.get("/api/v1/analytics/lead-dashboard", headers=headers_lead)
    assert res_dash_empty.status_code == 200
    dash_data = res_dash_empty.json()
    assert dash_data["total_team_members"] == 0
    assert dash_data["total_tasks"] == 0
    assert dash_data["overall_project_progress"] == 0

    # 3. Create Project
    res_proj = client.post(
        "/api/v1/projects",
        headers=headers_lead,
        json={"name": "Alpha Project", "description": "System build"},
    )
    assert res_proj.status_code == 201
    proj_id = res_proj.json()["id"]

    # 4. Create Team Member user
    res_member = client.post(
        "/api/v1/users",
        headers=headers_lead,
        json={
            "name": "Bob Developer",
            "email": "bob@example.com",
            "password": "password123",
            "role": "TEAM_MEMBER",
            "project_id": proj_id,
            "project_role": "Frontend Developer",
        },
    )
    assert res_member.status_code == 201
    member_id = res_member.json()["id"]

    # 5. Create Task assigned to Bob
    res_task = client.post(
        "/api/v1/tasks",
        headers=headers_lead,
        json={
            "project_id": proj_id,
            "title": "Build Navigation Bar",
            "description": "Create responsive header component",
            "assigned_to": member_id,
            "priority": "HIGH",
            "status": "TODO",
            "estimated_hours": 4.0,
        },
    )
    assert res_task.status_code == 201
    task_id = res_task.json()["id"]

    # 6. Login as Bob
    res_bob_login = client.post(
        "/api/v1/auth/login",
        json={"email": "bob@example.com", "password": "password123"},
    )
    bob_token = res_bob_login.json()["access_token"]
    headers_bob = {"Authorization": f"Bearer {bob_token}"}

    # Bob checks my-tasks
    res_bob_tasks = client.get("/api/v1/tasks?mine_only=true", headers=headers_bob)
    assert res_bob_tasks.status_code == 200
    assert len(res_bob_tasks.json()) == 1

    # Bob completes the task
    res_complete = client.patch(
        f"/api/v1/tasks/{task_id}/status?status=COMPLETED",
        headers=headers_bob,
    )
    assert res_complete.status_code == 200
    assert res_complete.json()["status"] == "COMPLETED"
    assert res_complete.json()["completed_at"] is not None

    # 7. Verify Lead Dashboard dynamic update (100% progress, notification, activity)
    res_dash_updated = client.get("/api/v1/analytics/lead-dashboard", headers=headers_lead)
    assert res_dash_updated.status_code == 200
    dash_updated = res_dash_updated.json()
    assert dash_updated["completed_tasks"] == 1
    assert dash_updated["overall_project_progress"] == 100
    assert len(dash_updated["recent_activity"]) > 0

    # Verify notification generated for Lead
    res_notifs = client.get("/api/v1/notifications", headers=headers_lead)
    assert res_notifs.status_code == 200
    assert len(res_notifs.json()) >= 1


def test_projects_sort_by_date_range():
    res_lead = client.post(
        "/api/v1/auth/register",
        json={"name": "Lead Sort", "email": "lead_sort@example.com", "password": "password123", "role": "TEAM_LEAD"},
    )
    assert res_lead.status_code == 201
    token = res_lead.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    early = client.post(
        "/api/v1/projects",
        headers=headers,
        json={
            "name": "Later Project",
            "start_date": "2026-02-10T00:00:00Z",
            "end_date": "2026-02-20T00:00:00Z",
        },
    )
    assert early.status_code == 201

    late = client.post(
        "/api/v1/projects",
        headers=headers,
        json={
            "name": "Earlier Project",
            "start_date": "2026-01-10T00:00:00Z",
            "end_date": "2026-01-20T00:00:00Z",
        },
    )
    assert late.status_code == 201

    earliest = client.get("/api/v1/projects?sort=earliest", headers=headers)
    assert earliest.status_code == 200
    earliest_names = [item["name"] for item in earliest.json()]
    assert earliest_names[0] == "Earlier Project"
    assert earliest_names[1] == "Later Project"

    latest = client.get("/api/v1/projects?sort=latest", headers=headers)
    assert latest.status_code == 200
    latest_names = [item["name"] for item in latest.json()]
    assert latest_names[0] == "Later Project"
    assert latest_names[1] == "Earlier Project"


def test_attachments_and_comments():
    # 1. Register Lead
    res_lead = client.post(
        "/api/v1/auth/register",
        json={"name": "Lead Test", "email": "lead_att@example.com", "password": "password123", "role": "TEAM_LEAD"}
    )
    assert res_lead.status_code == 201
    lead_token = res_lead.json()["access_token"]
    headers_lead = {"Authorization": f"Bearer {lead_token}"}

    # 2. Create Project & Task
    res_proj = client.post("/api/v1/projects", headers=headers_lead, json={"name": "Att Project"})
    proj_id = res_proj.json()["id"]

    res_task = client.post(
        "/api/v1/tasks",
        headers=headers_lead,
        json={"project_id": proj_id, "title": "Attachment Test Task"}
    )
    task_id = res_task.json()["id"]

    # 3. Add comment
    res_com = client.post(
        f"/api/v1/tasks/{task_id}/comments",
        headers=headers_lead,
        json={"comment": "First comment on task"}
    )
    assert res_com.status_code == 201
    assert res_com.json()["comment"] == "First comment on task"

    # 4. Upload attachment
    file_payload = ("test.txt", b"Hello Project Monitoring System", "text/plain")
    res_att = client.post(
        f"/api/v1/tasks/{task_id}/attachments",
        headers=headers_lead,
        files={"file": file_payload}
    )
    assert res_att.status_code == 201
    att_data = res_att.json()
    assert att_data["file_name"] == "test.txt"
    assert att_data["file_size"] > 0
    att_id = att_data["id"]

    # 5. List attachments
    res_list = client.get(f"/api/v1/tasks/{task_id}/attachments", headers=headers_lead)
    assert res_list.status_code == 200
    assert len(res_list.json()) == 1

    # 6. Delete attachment
    res_del = client.delete(f"/api/v1/tasks/attachments/{att_id}", headers=headers_lead)
    assert res_del.status_code == 204


def test_chat_and_groups():
    # Register Lead and Member
    res_lead = client.post(
        "/api/v1/auth/register",
        json={"name": "Lead Chat", "email": "lead_chat@example.com", "password": "password123", "role": "TEAM_LEAD"}
    )
    assert res_lead.status_code == 201
    lead_token = res_lead.json()["access_token"]
    lead_id = res_lead.json()["user"]["id"]
    headers_lead = {"Authorization": f"Bearer {lead_token}"}

    res_mem = client.post(
        "/api/v1/users",
        headers=headers_lead,
        json={"name": "Member Chat", "email": "mem_chat@example.com", "password": "password123", "role": "TEAM_MEMBER"}
    )
    assert res_mem.status_code == 201
    mem_id = res_mem.json()["id"]

    # 1-to-1 message
    res_msg = client.post(
        "/api/v1/messages",
        headers=headers_lead,
        json={"receiver_id": mem_id, "message": "Hello Member!"}
    )
    assert res_msg.status_code == 201
    assert res_msg.json()["message"] == "Hello Member!"

    # Log in as member to check unread messages
    res_mem_login = client.post(
        "/api/v1/auth/login",
        json={"email": "mem_chat@example.com", "password": "password123"}
    )
    assert res_mem_login.status_code == 200
    headers_mem = {"Authorization": f"Bearer {res_mem_login.json()['access_token']}"}

    # Verify member unread count is 1
    res_unread = client.get("/api/v1/messages/unread/count", headers=headers_mem)
    assert res_unread.status_code == 200
    assert res_unread.json()["unread_count"] == 1
    assert res_unread.json()["unread_by_sender"][str(lead_id)] == 1

    # Member reads conversation
    res_read = client.get(f"/api/v1/messages/{lead_id}", headers=headers_mem)
    assert res_read.status_code == 200

    # Verify unread count is now 0
    res_unread_after = client.get("/api/v1/messages/unread/count", headers=headers_mem)
    assert res_unread_after.status_code == 200
    assert res_unread_after.json()["unread_count"] == 0

    # Get conversation history for lead
    res_hist = client.get(f"/api/v1/messages/{mem_id}", headers=headers_lead)
    assert res_hist.status_code == 200
    assert len(res_hist.json()) == 1

    # Create Group
    res_grp = client.post(
        "/api/v1/groups",
        headers=headers_lead,
        json={"name": "Frontend Squad", "description": "UI development team", "member_ids": [mem_id]}
    )
    assert res_grp.status_code == 201
    grp_id = res_grp.json()["id"]

    # Send group message
    res_gmsg = client.post(
        f"/api/v1/groups/{grp_id}/messages",
        headers=headers_lead,
        json={"message": "Welcome to Frontend Squad!"}
    )
    assert res_gmsg.status_code == 201

    # Get group messages
    res_glist = client.get(f"/api/v1/groups/{grp_id}/messages", headers=headers_lead)
    assert res_glist.status_code == 200
    assert len(res_glist.json()) == 1


def test_overdue_tasks_and_analytics():
    # Register Lead
    res_lead = client.post(
        "/api/v1/auth/register",
        json={"name": "Lead Overdue", "email": "lead_overdue@example.com", "password": "password123", "role": "TEAM_LEAD"}
    )
    assert res_lead.status_code == 201
    lead_token = res_lead.json()["access_token"]
    headers_lead = {"Authorization": f"Bearer {lead_token}"}

    # Empty analytics
    res_ana_empty = client.get("/api/v1/analytics/metrics", headers=headers_lead)
    assert res_ana_empty.status_code == 200
    assert res_ana_empty.json()["has_data"] is False

    # Create Project
    res_proj = client.post("/api/v1/projects", headers=headers_lead, json={"name": "Deadline Project"})
    proj_id = res_proj.json()["id"]

    # Create Overdue task (due date in 2020)
    res_task = client.post(
        "/api/v1/tasks",
        headers=headers_lead,
        json={
            "project_id": proj_id,
            "title": "Old Overdue Task",
            "due_date": "2020-01-01T12:00:00Z",
            "status": "TODO"
        }
    )
    assert res_task.status_code == 201
    assert res_task.json()["is_overdue"] is True

    # Check analytics with data
    res_ana = client.get("/api/v1/analytics/metrics", headers=headers_lead)
    assert res_ana.status_code == 200
    ana_data = res_ana.json()
    assert ana_data["has_data"] is True
    assert ana_data["overdue_count"] == 1

