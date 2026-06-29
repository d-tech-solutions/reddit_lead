import sys
import os
from fastapi.testclient import TestClient

# Add parent directory to path to enable importing app
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.main import app
from app.database import SessionLocal
from app.models import User, LeadAnalysis, RedditPost, UserPreferences

client = TestClient(app)

def test_endpoints():
    print("=== STARTING API ENDPOINTS TESTS ===")
    
    # 1. Test Registration
    print("\n1. Testing /auth/register...")
    test_email = "testuser@leadradar.com"
    test_password = "password123"
    
    # Clean up test user & post if exists from a previous bad run
    db = SessionLocal()
    try:
        user_to_del = db.query(User).filter(User.email == test_email).first()
        if user_to_del:
            db.delete(user_to_del)
        db.query(RedditPost).filter(RedditPost.reddit_id == "dummy_post_999").delete()
        db.commit()
    finally:
        db.close()
        
    response = client.post("/auth/register", json={
        "email": test_email,
        "password": test_password,
        "full_name": "Test User"
    })
    
    assert response.status_code == 200, f"Registration failed: {response.text}"
    token_data = response.json()
    assert "access_token" in token_data
    token = token_data["access_token"]
    print("Registration successfully passed!")
    
    headers = {"Authorization": f"Bearer {token}"}
    
    # 2. Test /auth/me
    print("\n2. Testing /auth/me...")
    response = client.get("/auth/me", headers=headers)
    assert response.status_code == 200, f"Fetch profile failed: {response.text}"
    me_data = response.json()
    assert me_data["email"] == test_email
    print("Profile fetch successfully passed!")
    
    # 3. Test Onboarding Endpoints
    print("\n3. Testing Onboarding Endpoints...")
    response = client.post("/onboarding/start", headers=headers)
    assert response.status_code == 200, f"Start onboarding failed: {response.text}"
    start_data = response.json()
    assert start_data["status"] == "in_progress"
    print("Start onboarding successfully passed!")
    
    response = client.post("/onboarding/respond", json={"response": "I build SaaS apps"}, headers=headers)
    assert response.status_code == 200, f"Respond onboarding failed: {response.text}"
    respond_data = response.json()
    print("Respond onboarding successfully passed!")
    
    response = client.get("/onboarding/status", headers=headers)
    assert response.status_code == 200, f"Get onboarding status failed: {response.text}"
    status_data = response.json()
    assert status_data["status"] in ["in_progress", "completed"]
    print("Get onboarding status successfully passed!")
    
    # 4. Seed a post and test lead fetch and CRM status updates
    print("\n4. Testing Leads Fetch & CRM updates...")
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == test_email).first()
        # Create a dummy Reddit post
        post = RedditPost(
            reddit_id="dummy_post_999",
            title="Need developer for Python FastAPI web project",
            content="Hi! I need a developer to build a Python FastAPI web project.",
            subreddit="FastAPI",
            url="https://reddit.com/r/FastAPI/dummy_post_999",
            created_utc=datetime.datetime.utcnow()
        )
        db.add(post)
        db.flush()
        
        # Create a dummy LeadAnalysis for this user
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
        db.add(analysis)
        db.commit()
        
        post_id = post.id
    except Exception as e:
        db.rollback()
        raise e
    finally:
        db.close()
        
    # Get leads
    response = client.get("/leads", headers=headers)
    assert response.status_code == 200, f"Get leads failed: {response.text}"
    leads_list = response.json()
    assert len(leads_list) >= 1
    print("Get leads successfully passed!")
    
    # Get lead details
    response = client.get(f"/leads/{post_id}", headers=headers)
    assert response.status_code == 200, f"Get lead details failed: {response.text}"
    details = response.json()
    assert details["analysis"]["score"] == 90
    print("Get lead details successfully passed!")
    
    # Update CRM status
    response = client.patch(f"/leads/{post_id}/status", json={"status": "Replied"}, headers=headers)
    assert response.status_code == 200, f"Update status failed: {response.text}"
    print("Update lead status successfully passed!")
    
    # Add note
    response = client.post(f"/leads/{post_id}/notes", json={"text": "Sent initial reply"}, headers=headers)
    assert response.status_code == 200, f"Add note failed: {response.text}"
    note_resp = response.json()
    assert len(note_resp["notes"]) == 1
    print("Add note successfully passed!")
    
    # Save lead
    response = client.post(f"/leads/{post_id}/save", headers=headers)
    assert response.status_code == 200, f"Save lead failed: {response.text}"
    assert response.json()["saved"] is True
    print("Save lead successfully passed!")
    
    # Unsave lead
    response = client.delete(f"/leads/{post_id}/save", headers=headers)
    assert response.status_code == 200, f"Unsave lead failed: {response.text}"
    assert response.json()["saved"] is False
    print("Unsave lead successfully passed!")
    
    # 5. Test Superadmin stats
    print("\n5. Testing Admin Authorization...")
    # Normal user should be rejected from admin endpoints
    response = client.get("/admin/stats", headers=headers)
    assert response.status_code == 403, f"Standard user was not forbidden from admin stats: {response.text}"
    print("Admin route restriction for standard users successfully passed!")
    
    # Seeded superadmin user login and check
    response = client.post("/auth/login", json={
        "email": "admin@leadradar.com",
        "password": "1111111111"
    })
    assert response.status_code == 200, f"Superadmin login failed: {response.text}"
    admin_token = response.json()["access_token"]
    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    
    response = client.get("/admin/stats", headers=admin_headers)
    assert response.status_code == 200, f"Admin stats failed: {response.text}"
    stats_data = response.json()
    assert "total_users" in stats_data
    assert "total_posts_collected" in stats_data
    print("Admin stats access for superadmin successfully passed!")
    
    # 6. Clean up test users and data
    print("\n6. Cleaning up test data...")
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == test_email).first()
        if user:
            db.delete(user)
        db.query(RedditPost).filter(RedditPost.reddit_id == "dummy_post_999").delete()
        db.commit()
    finally:
        db.close()
        
    print("Cleanup completed.")
    print("\n=== ALL ENDPOINT TESTS PASSED SUCCESSFULLY! ===")

if __name__ == "__main__":
    import datetime
    test_endpoints()
