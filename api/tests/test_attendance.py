import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.main import app
from app.core.database import Base, get_db
from app.models.all_models import User
from app.core.security import hash_password

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


def test_attendance_lifecycle():
    # 1. Register a Team Lead
    res_lead = client.post(
        "/api/v1/auth/register",
        json={"name": "Attend Lead", "email": "att_lead@example.com", "password": "password123", "role": "TEAM_LEAD"},
    )
    assert res_lead.status_code == 201
    lead_token = res_lead.json()["access_token"]
    headers_lead = {"Authorization": f"Bearer {lead_token}"}

    # 2. Add a Team Member directly in db
    db = TestingSessionLocal()
    member = User(name="Attend Member", email="att_mem@example.com", password_hash=hash_password("password123"), role="TEAM_MEMBER")
    db.add(member)
    db.commit()
    db.refresh(member)
    db.close()

    res_mem_login = client.post(
        "/api/v1/auth/login",
        json={"email": "att_mem@example.com", "password": "password123"},
    )
    assert res_mem_login.status_code == 200
    mem_token = res_mem_login.json()["access_token"]
    headers_mem = {"Authorization": f"Bearer {mem_token}"}

    # 3. Member checks today's attendance before any punch
    res_today_before = client.get("/api/v1/attendance/me/today", headers=headers_mem)
    assert res_today_before.status_code == 200
    data_before = res_today_before.json()
    assert data_before["is_clocked_in"] is False
    assert len(data_before["punches"]) == 0

    # 4. Clock In
    res_clock_in = client.post("/api/v1/attendance/punch", json={"punch_type": "CLOCK_IN"}, headers=headers_mem)
    assert res_clock_in.status_code == 200
    data_in = res_clock_in.json()
    assert data_in["is_clocked_in"] is True
    assert data_in["is_on_break"] is False
    assert len(data_in["punches"]) == 1
    assert data_in["punches"][0]["punch_type"] == "CLOCK_IN"

    # 5. Start Break
    res_break_start = client.post("/api/v1/attendance/punch", json={"punch_type": "BREAK_START"}, headers=headers_mem)
    assert res_break_start.status_code == 200
    data_break = res_break_start.json()
    assert data_break["is_on_break"] is True

    # 6. End Break
    res_break_end = client.post("/api/v1/attendance/punch", json={"punch_type": "BREAK_END"}, headers=headers_mem)
    assert res_break_end.status_code == 200
    data_resume = res_break_end.json()
    assert data_resume["is_on_break"] is False
    assert data_resume["is_clocked_in"] is True

    # 7. Clock Out
    res_clock_out = client.post("/api/v1/attendance/punch", json={"punch_type": "CLOCK_OUT"}, headers=headers_mem)
    assert res_clock_out.status_code == 200
    data_out = res_clock_out.json()
    assert data_out["is_clocked_in"] is False
    assert data_out["last_punch_type"] == "CLOCK_OUT"

    # 8. Monthly attendance
    res_monthly = client.get("/api/v1/attendance/me/monthly", headers=headers_mem)
    assert res_monthly.status_code == 200
    monthly_records = res_monthly.json()
    assert len(monthly_records) >= 1

    # 9. Lead views daily attendance snapshot
    res_team_daily = client.get("/api/v1/attendance/team/daily", headers=headers_lead)
    assert res_team_daily.status_code == 200
    snapshot = res_team_daily.json()
    assert snapshot["total_members"] >= 2

    # 10. Lead views report
    from datetime import datetime, timezone
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    res_report = client.get(f"/api/v1/attendance/team/report?start_date={today_str}&end_date={today_str}", headers=headers_lead)
    assert res_report.status_code == 200
    assert len(res_report.json()) >= 1
