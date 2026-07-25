import pytest
import datetime
from app.models import RedditPost, User, UserPreferences, RedditPostIntelligence
from app.ai_service import generate_embedding, extract_post_intelligence
from app.crud.post import create_post_intelligence, get_post_intelligence
from app.onboarding_service import initialize_onboarding, process_onboarding_turn
from app.auth_service import get_password_hash

def test_generate_embedding():
    # Test fallback/mock embedding generation
    vector = generate_embedding("Hello test world")
    assert isinstance(vector, list)
    assert len(vector) == 1536
    assert all(isinstance(x, float) for x in vector)

def test_extract_post_intelligence():
    # Test fallback/mock intelligence extraction
    intel = extract_post_intelligence("Need custom automation software", "Hi! I need automated software for my store.")
    assert "problem" in intel
    assert "industry" in intel
    assert "services_needed" in intel
    assert "buying_intent" in intel
    assert "urgency" in intel
    assert "estimated_budget" in intel
    assert "summary" in intel
    assert isinstance(intel["services_needed"], list)

def test_crud_post_intelligence(db_session):
    # Setup dummy Reddit post
    post = RedditPost(
        reddit_id="intel_post_001",
        title="Need developer for Python FastAPI web project",
        content="Hi! I need a developer to build a Python FastAPI web project.",
        subreddit="FastAPI",
        url="https://reddit.com/r/FastAPI/intel_post_001",
        created_utc=datetime.datetime.utcnow()
    )
    db_session.add(post)
    db_session.flush()

    # Save intelligence
    mock_vector = [0.05] * 1536
    intel_data = {
        "post_id": post.id,
        "problem": "Wants FastAPI web project",
        "industry": "Software",
        "services_needed": ["Web Development"],
        "buying_intent": "High",
        "urgency": "High",
        "estimated_budget": "$3000",
        "summary": "Need developer for FastAPI",
        "embedding": mock_vector
    }

    db_intel = create_post_intelligence(db_session, intel_data)
    db_session.commit()

    assert db_intel.id is not None
    assert db_intel.post_id == post.id
    assert db_intel.industry == "Software"
    assert db_intel.services_needed == ["Web Development"]
    
    # Retrieve intelligence
    retrieved = get_post_intelligence(db_session, post.id)
    assert retrieved is not None
    assert retrieved.problem == "Wants FastAPI web project"
    assert isinstance(retrieved.embedding, list)
    assert len(retrieved.embedding) == 1536
    assert retrieved.embedding[0] == pytest.approx(0.05)

def test_onboarding_embedding_generation(db_session, client):
    # Register and setup user
    hashed_pw = get_password_hash("password123")
    user = User(email="onboarding_embed@leadradar.com", hashed_password=hashed_pw, full_name="Embed User", is_admin=False)
    db_session.add(user)
    db_session.flush()

    # Initialize onboarding
    initialize_onboarding(db_session, user_id=user.id)
    prefs = db_session.query(UserPreferences).filter(UserPreferences.user_id == user.id).first()
    assert prefs is not None
    assert prefs.onboarding_status == "in_progress"
    assert prefs.embedding is None

    # Simulate answering the prompt to trigger completion/embedding generation.
    # We will mock the onboarding service return so it triggers completion.
    # Log in
    login_resp = client.post("/auth/login", json={
        "email": "onboarding_embed@leadradar.com",
        "password": "password123"
    })
    token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Respond to onboarding
    # Since settings.OPENAI_API_KEY is not set or mock, it will do a mock turn.
    # In a mock turn, it does in_progress first. We'll do multiple turns or verify the completion block works directly.
    # Let's verify the completion logic directly via onboarding_service:
    from app.onboarding_service import process_onboarding_turn
    # Force mock onboarding completion
    # We can process it directly by overriding question_count or confidence
    prefs.question_count = 6 # Next turn will hit max limit (6) or we can mock response
    db_session.commit()

    result = process_onboarding_turn(db_session, "I want to ignore tutorials.", user_id=user.id)
    assert result["status"] == "completed"
    
    # Check preferences table for embedding
    db_session.refresh(prefs)
    assert prefs.onboarding_status == "completed"
    assert prefs.embedding is not None
    assert len(prefs.embedding) == 1536
    assert all(isinstance(x, float) for x in prefs.embedding)
