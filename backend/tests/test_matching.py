import pytest
import datetime
from app.models import User, RedditPost, UserPreferences, RedditPostIntelligence, LeadAnalysis
from app.analyzer import (
    python_cosine_similarity,
    process_single_post_intelligence,
    match_post_to_users_pipeline,
    analyze_pending_posts
)
from app.auth_service import get_password_hash
import json

@pytest.fixture(autouse=True)
def mock_ai_services(monkeypatch):
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
        # Match if services overlap
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

def test_python_cosine_similarity():
    # Identical vectors
    v1 = [1.0, 2.0, 3.0]
    v2 = [1.0, 2.0, 3.0]
    assert python_cosine_similarity(v1, v2) == pytest.approx(1.0)

    # Orthogonal vectors
    v3 = [1.0, 0.0]
    v4 = [0.0, 1.0]
    assert python_cosine_similarity(v3, v4) == pytest.approx(0.0)

    # Opposite vectors
    v5 = [1.0, -1.0]
    v6 = [-1.0, 1.0]
    assert python_cosine_similarity(v5, v6) == pytest.approx(-1.0)

    # Empty or zero magnitude
    assert python_cosine_similarity([], []) == 0.0
    assert python_cosine_similarity([0.0], [0.0]) == 0.0

def test_process_single_post_intelligence(db_session):
    # Setup post
    post = RedditPost(
        reddit_id="matching_post_001",
        title="Looking for React developer to build SaaS MVP",
        content="Hi! I need a frontend dev to build a custom dashboard for SaaS.",
        subreddit="SaaS",
        url="https://reddit.com/r/SaaS/matching_post_001",
        created_utc=datetime.datetime.utcnow()
    )
    db_session.add(post)
    db_session.commit()

    # Process intelligence
    intel = process_single_post_intelligence(db_session, post.id)
    assert intel is not None
    assert intel.post_id == post.id
    assert intel.buying_intent == "High"  # Mock default
    assert isinstance(intel.embedding, list)
    assert len(intel.embedding) == 1536

    # Test cache reuse
    intel_cached = process_single_post_intelligence(db_session, post.id)
    assert intel_cached.id == intel.id

def test_matching_pipeline_vector_and_matcher(db_session):
    # 1. Setup candidate user with profile matching React development
    hashed_pw = get_password_hash("password123")
    user = User(email="candidate@leadradar.com", hashed_password=hashed_pw, full_name="Candidate", is_admin=False)
    db_session.add(user)
    db_session.flush()

    # Setup profile embedding pointing to React/Web Development
    # Use 1536 size. Let's make it highly similar (0.01) to post default mock (0.01)
    prefs = UserPreferences(
        user_id=user.id,
        onboarding_status="completed",
        onboarding_history=[],
        question_count=6,
        confidence=0.9,
        profile_json={
            "services": ["Web Development", "React Development"],
            "desired_opportunities": ["SaaS MVP builds"]
        },
        embedding=[0.01] * 1536
    )
    db_session.add(prefs)

    # 2. Setup non-candidate user with orthogonal embedding
    non_candidate = User(email="ignored@leadradar.com", hashed_password=hashed_pw, full_name="Ignored", is_admin=False)
    db_session.add(non_candidate)
    db_session.flush()

    ignored_prefs = UserPreferences(
        user_id=non_candidate.id,
        onboarding_status="completed",
        confidence=0.95,
        profile_json={
            "services": ["Mobile Apps"],
            "desired_opportunities": ["Flutter apps"]
        },
        embedding=[-0.01] * 1536 # Opposite vector (orthogonal/negative similarity)
    )
    db_session.add(ignored_prefs)

    # Setup post
    post = RedditPost(
        reddit_id="matching_post_002",
        title="Need React developer",
        content="React project needs building.",
        subreddit="SaaS",
        url="https://reddit.com/r/SaaS/matching_post_002",
        created_utc=datetime.datetime.utcnow()
    )
    db_session.add(post)
    db_session.commit()

    # Match post against users
    res = match_post_to_users_pipeline(db_session, post.id, top_n=5)
    assert res["matched_users"] == 1 # Only Candidate should qualify

    # Check LeadAnalysis rows
    candidate_analysis = db_session.query(LeadAnalysis).filter(
        LeadAnalysis.post_id == post.id,
        LeadAnalysis.user_id == user.id
    ).first()
    assert candidate_analysis is not None
    assert candidate_analysis.relevant is True
    assert candidate_analysis.score == 85

    ignored_analysis = db_session.query(LeadAnalysis).filter(
        LeadAnalysis.post_id == post.id,
        LeadAnalysis.user_id == non_candidate.id
    ).first()
    # Ignored is not evaluated by match_post_to_users_pipeline since it's not in the candidates list
    assert ignored_analysis is None

def test_analyze_pending_posts_flow(db_session):
    # Setup candidate user
    hashed_pw = get_password_hash("password123")
    user = User(email="analyzer_candidate@leadradar.com", hashed_password=hashed_pw, full_name="Candidate", is_admin=False)
    db_session.add(user)
    db_session.flush()

    prefs = UserPreferences(
        user_id=user.id,
        onboarding_status="completed",
        profile_json={"services": ["Automation"]},
        embedding=[0.01] * 1536
    )
    db_session.add(prefs)

    # Setup non-candidate user
    ignored_user = User(email="analyzer_ignored@leadradar.com", hashed_password=hashed_pw, is_admin=False)
    db_session.add(ignored_user)
    db_session.flush()

    ignored_prefs = UserPreferences(
        user_id=ignored_user.id,
        onboarding_status="completed",
        profile_json={"services": ["Mobile"]},
        embedding=[-0.01] * 1536
    )
    db_session.add(ignored_prefs)

    # Setup post
    post = RedditPost(
        reddit_id="matching_post_003",
        title="Need python help",
        content="Python code help.",
        subreddit="SaaS",
        url="https://reddit.com/r/SaaS/matching_post_003",
        created_utc=datetime.datetime.utcnow()
    )
    db_session.add(post)
    db_session.commit()

    # Trigger analyze_pending_posts for Candidate
    res1 = analyze_pending_posts(db_session, user_id=user.id, limit=5)
    assert res1["processed"] == 1
    assert res1["successful"] == 1

    ans1 = db_session.query(LeadAnalysis).filter(LeadAnalysis.post_id == post.id, LeadAnalysis.user_id == user.id).first()
    assert ans1 is not None
    assert ans1.relevant is True

    # Trigger analyze_pending_posts for Ignored User
    res2 = analyze_pending_posts(db_session, user_id=ignored_user.id, limit=5)
    assert res2["processed"] == 1
    assert res2["successful"] == 1

    ans2 = db_session.query(LeadAnalysis).filter(LeadAnalysis.post_id == post.id, LeadAnalysis.user_id == ignored_user.id).first()
    assert ans2 is not None
    assert ans2.relevant is False
    assert ans2.score == 0 # Saved with zero score because vector similarity failed
