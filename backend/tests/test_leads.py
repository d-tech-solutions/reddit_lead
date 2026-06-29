import pytest
import datetime
from app.models import User, RedditPost, LeadAnalysis, UserPreferences
from app.auth_service import get_password_hash

def test_leads_and_crm_flow(client, db_session):
    # 1. Setup users (regular user + admin user)
    hashed_pw = get_password_hash("password123")
    
    user = User(email="crm_user@leadradar.com", hashed_password=hashed_pw, full_name="CRM User", is_admin=False)
    admin = User(email="crm_admin@leadradar.com", hashed_password=hashed_pw, full_name="CRM Admin", is_admin=True)
    db_session.add(user)
    db_session.add(admin)
    db_session.flush()
    
    # Setup preferences
    prefs = UserPreferences(
        user_id=user.id,
        onboarding_status="completed",
        onboarding_history=[],
        question_count=0,
        confidence=0.9,
        profile_json={"services": ["FastAPI"]}
    )
    admin_prefs = UserPreferences(
        user_id=admin.id,
        onboarding_status="not_started",
        onboarding_history=[],
        question_count=0,
        confidence=0.0,
        profile_json=None
    )
    db_session.add(prefs)
    db_session.add(admin_prefs)
    
    # 2. Setup dummy Reddit post & LeadAnalysis matching crm_user
    post = RedditPost(
        reddit_id="test_post_111",
        title="Need developer for Python FastAPI web project",
        content="Hi! I need a developer to build a Python FastAPI web project.",
        subreddit="FastAPI",
        url="https://reddit.com/r/FastAPI/test_post_111",
        created_utc=datetime.datetime.utcnow()
    )
    db_session.add(post)
    db_session.flush()
    
    analysis = LeadAnalysis(
        post_id=post.id,
        user_id=user.id,
        relevant=True,
        score=90,
        industry="Software",
        urgency="High",
        intent="Build FastAPI web project",
        estimated_budget="$3000",
        recommended_service="Web Development",
        summary="Client needs developer for FastAPI web project.",
        suggested_reply="Hi! I noticed your post and would love to help you build your Python FastAPI web project.",
        match_reasoning=["FastAPI match", "Python match"]
    )
    db_session.add(analysis)
    db_session.commit()
    
    # 3. Log in as standard user
    login_resp = client.post("/auth/login", json={
        "email": "crm_user@leadradar.com",
        "password": "password123"
    })
    token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    
    # 4. Get Leads list
    leads_resp = client.get("/leads", headers=headers)
    assert leads_resp.status_code == 200
    leads = leads_resp.json()
    assert len(leads) >= 1
    assert leads[0]["reddit_id"] == "test_post_111"
    
    # 5. Get Lead details
    details_resp = client.get(f"/leads/{post.id}", headers=headers)
    assert details_resp.status_code == 200
    details = details_resp.json()
    assert details["analysis"]["score"] == 90
    
    # 6. Update lead status
    status_resp = client.patch(f"/leads/{post.id}/status", json={"status": "Replied"}, headers=headers)
    assert status_resp.status_code == 200
    
    # 7. Add notes
    note_resp = client.post(f"/leads/{post.id}/notes", json={"text": "Left initial pitch reply"}, headers=headers)
    assert note_resp.status_code == 200
    assert len(note_resp.json()["notes"]) == 1
    
    # 8. Save Lead
    save_resp = client.post(f"/leads/{post.id}/save", headers=headers)
    assert save_resp.status_code == 200
    assert save_resp.json()["saved"] is True
    
    # 9. Test authorization block
    admin_stats_resp = client.get("/admin/stats", headers=headers)
    assert admin_stats_resp.status_code == 403
    
    # 10. Log in as admin and verify admin stats access
    admin_login_resp = client.post("/auth/login", json={
        "email": "crm_admin@leadradar.com",
        "password": "password123"
    })
    admin_token = admin_login_resp.json()["access_token"]
    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    
    admin_stats_resp = client.get("/admin/stats", headers=admin_headers)
    assert admin_stats_resp.status_code == 200
    stats = admin_stats_resp.json()
    assert stats["total_users"] == 2
