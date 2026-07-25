import pytest
import datetime
from app.celery_app import celery_app
from app.models import User, RedditPost, UserPreferences, LeadAnalysis
from app.tasks import fetch_and_match_leads_task, analyze_user_pending_leads_task
from app.auth_service import get_password_hash

# Setup eager execution for celery in test environment
@pytest.fixture(autouse=True)
def setup_celery_eager():
    old_eager = celery_app.conf.task_always_eager
    celery_app.conf.task_always_eager = True
    yield
    celery_app.conf.task_always_eager = old_eager

@pytest.fixture(autouse=True)
def mock_ai_services(monkeypatch):
    # Mock generate_embedding

    # Mock generate_embedding
    def mock_emb(text):
        if "React" in text or "python" in text:
            return [0.01] * 1536
        return [-0.01] * 1536
    monkeypatch.setattr("app.analyzer.generate_embedding", mock_emb)
    monkeypatch.setattr("app.ai_service.generate_embedding", mock_emb)

    # Mock extract_post_intelligence
    def mock_extract(title, content):
        return {
            "problem": "Client needs software developer",
            "industry": "Software",
            "services_needed": ["Web Development"],
            "buying_intent": "High",
            "urgency": "High",
            "estimated_budget": "$3000",
            "summary": "Need developer"
        }
    monkeypatch.setattr("app.analyzer.extract_post_intelligence", mock_extract)

    # Mock personal_match_lead
    def mock_personal(profile, intelligence, title):
        services = profile.get("services", [])
        if "React Development" in services or "Automation" in services:
            return {
                "relevant": True,
                "score": 85,
                "recommended_service": "Web Development",
                "match_reasoning": ["React match", "Web match"],
                "suggested_reply": "Hi, I saw your post."
            }
        return {
            "relevant": False,
            "score": 0,
            "recommended_service": "General",
            "match_reasoning": ["No match"],
            "suggested_reply": ""
        }
    monkeypatch.setattr("app.analyzer.personal_match_lead", mock_personal)

    # Mock fetch_subreddit_posts to return a predictable list
    def mock_fetch(subreddit):
        return [{
            "reddit_id": f"celery_post_{subreddit}",
            "title": f"Need React developer helper in {subreddit}",
            "content": "Building React dashboard.",
            "author": "john_doe",
            "subreddit": subreddit,
            "url": f"https://reddit.com/r/{subreddit}/celery_post_{subreddit}",
            "created_utc": datetime.datetime.utcnow()
        }]
    monkeypatch.setattr("app.collector.fetch_subreddit_posts", mock_fetch)

def test_fetch_and_match_leads_task(db_session, monkeypatch):
    # Patch tasks database session to share the active db_session
    monkeypatch.setattr(db_session, "close", lambda: None)
    monkeypatch.setattr("app.tasks.SessionLocal", lambda: db_session)

    # Setup candidate user with React/Web profile
    hashed_pw = get_password_hash("password123")
    user = User(email="celery_user@leadradar.com", hashed_password=hashed_pw, full_name="Celery User", is_admin=False)
    db_session.add(user)
    db_session.flush()

    prefs = UserPreferences(
        user_id=user.id,
        onboarding_status="completed",
        profile_json={"services": ["React Development"]},
        embedding=[0.01] * 1536
    )
    db_session.add(prefs)
    db_session.commit()

    # Override monitored subreddits to test only one to run fast
    monkeypatch.setattr("app.config.settings.MONITORED_SUBREDDITS", "SaaS")

    # Run celery task asynchronously (which runs synchronously under eager configuration)
    result = fetch_and_match_leads_task.delay().get()
    
    assert result["fetched"] == 1
    assert result["saved"] == 1
    assert result["matched_users"] == 1

    # Check that lead analysis record is enqueued in database
    analysis = db_session.query(LeadAnalysis).filter(
        LeadAnalysis.user_id == user.id
    ).first()
    assert analysis is not None
    assert analysis.relevant is True
    assert analysis.score == 85

def test_analyze_user_pending_leads_task(db_session, monkeypatch):
    # Patch tasks database session to share the active db_session
    monkeypatch.setattr(db_session, "close", lambda: None)
    monkeypatch.setattr("app.tasks.SessionLocal", lambda: db_session)

    # Setup user
    hashed_pw = get_password_hash("password123")
    user = User(email="celery_user_2@leadradar.com", hashed_password=hashed_pw, is_admin=False)
    db_session.add(user)
    db_session.flush()

    prefs = UserPreferences(
        user_id=user.id,
        onboarding_status="completed",
        profile_json={"services": ["Automation"]},
        embedding=[0.01] * 1536
    )
    db_session.add(prefs)

    # Setup post already saved in database
    post = RedditPost(
        reddit_id="celery_pending_post_001",
        title="Need python automate helper",
        content="Help me automate.",
        subreddit="SaaS",
        url="https://reddit.com/r/SaaS/celery_pending_post_001",
        created_utc=datetime.datetime.utcnow()
    )
    db_session.add(post)
    db_session.commit()

    # Run celery user analyze task
    result = analyze_user_pending_leads_task.delay(user.id, limit=5).get()
    assert result["processed"] == 1
    assert result["successful"] == 1

    analysis = db_session.query(LeadAnalysis).filter(
        LeadAnalysis.user_id == user.id,
        LeadAnalysis.post_id == post.id
    ).first()
    assert analysis is not None
    assert analysis.relevant is True
    assert analysis.score == 85


def test_get_task_status_endpoint(client, monkeypatch):
    # Mock AsyncResult
    class MockAsyncResult:
        def __init__(self, task_id, app=None):
            self.task_id = task_id
            self.status = "SUCCESS"
        def ready(self):
            return True
        @property
        def result(self):
            return {"status": "success"}
            
    monkeypatch.setattr("celery.result.AsyncResult", MockAsyncResult)
    
    response = client.get("/tasks/mock_task_id_123")
    assert response.status_code == 200
    data = response.json()
    assert data["task_id"] == "mock_task_id_123"
    assert data["status"] == "SUCCESS"
    assert data["result"] == {"status": "success"}
