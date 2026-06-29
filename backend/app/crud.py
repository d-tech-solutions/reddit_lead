from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Optional, Dict, Any
import datetime

from app.models import User, RedditPost, LeadAnalysis, UserPreferences

# --- USER CRUD ---

def get_user_by_email(db: Session, email: str) -> Optional[User]:
    return db.query(User).filter(User.email == email).first()

def get_user_by_id(db: Session, user_id: int) -> Optional[User]:
    return db.query(User).filter(User.id == user_id).first()

def get_all_users(db: Session) -> List[User]:
    return db.query(User).all()

def create_user(db: Session, email: str, hashed_password: str, full_name: Optional[str] = None, is_admin: bool = False) -> User:
    user = User(
        email=email,
        hashed_password=hashed_password,
        full_name=full_name,
        is_admin=is_admin
    )
    db.add(user)
    db.flush()
    return user

# --- USER PREFERENCES CRUD ---

def get_user_preferences(db: Session, user_id: int) -> Optional[UserPreferences]:
    return db.query(UserPreferences).filter(UserPreferences.user_id == user_id).first()

def create_user_preferences(db: Session, user_id: int) -> UserPreferences:
    prefs = UserPreferences(
        user_id=user_id,
        onboarding_status="not_started",
        onboarding_history=[],
        question_count=0,
        confidence=0.0,
        profile_json=None
    )
    db.add(prefs)
    db.flush()
    return prefs

def update_user_preferences(
    db: Session, 
    user_id: int, 
    onboarding_status: Optional[str] = None,
    onboarding_history: Optional[list] = None,
    question_count: Optional[int] = None,
    confidence: Optional[float] = None,
    profile_json: Optional[dict] = None
) -> Optional[UserPreferences]:
    prefs = get_user_preferences(db, user_id=user_id)
    if not prefs:
        return None
    
    if onboarding_status is not None:
        prefs.onboarding_status = onboarding_status
    if onboarding_history is not None:
        prefs.onboarding_history = onboarding_history
    if question_count is not None:
        prefs.question_count = question_count
    if confidence is not None:
        prefs.confidence = confidence
    if profile_json is not None:
        prefs.profile_json = profile_json
        
    db.commit()
    return prefs

# --- REDDIT POSTS CRUD ---

def get_post_by_reddit_id(db: Session, reddit_id: str) -> Optional[RedditPost]:
    return db.query(RedditPost).filter(RedditPost.reddit_id == reddit_id).first()

def get_post_by_id(db: Session, post_id: int) -> Optional[RedditPost]:
    return db.query(RedditPost).filter(RedditPost.id == post_id).first()

def create_reddit_post(db: Session, post_data: dict) -> RedditPost:
    post = RedditPost(
        reddit_id=post_data["reddit_id"],
        title=post_data["title"],
        content=post_data.get("content"),
        author=post_data.get("author"),
        subreddit=post_data["subreddit"],
        url=post_data.get("url"),
        created_utc=post_data["created_utc"]
    )
    db.add(post)
    return post

def get_pending_posts_for_user(db: Session, user_id: int, limit: int = 10) -> List[RedditPost]:
    return (
        db.query(RedditPost)
        .outerjoin(
            LeadAnalysis, 
            (LeadAnalysis.post_id == RedditPost.id) & (LeadAnalysis.user_id == user_id)
        )
        .filter(LeadAnalysis.id == None)
        .order_by(RedditPost.created_utc.desc())
        .limit(limit)
        .all()
    )

# --- LEAD ANALYSIS CRUD ---

def get_lead_analysis(db: Session, post_id: int, user_id: int) -> Optional[LeadAnalysis]:
    return db.query(LeadAnalysis).filter(
        LeadAnalysis.post_id == post_id,
        LeadAnalysis.user_id == user_id
    ).first()

def create_lead_analysis(db: Session, analysis_data: dict) -> LeadAnalysis:
    analysis = LeadAnalysis(
        post_id=analysis_data["post_id"],
        user_id=analysis_data["user_id"],
        relevant=analysis_data.get("relevant", False),
        score=analysis_data.get("score", 0),
        industry=analysis_data.get("industry", "General"),
        urgency=analysis_data.get("urgency", "Low"),
        intent=analysis_data.get("intent", "Unknown"),
        estimated_budget=analysis_data.get("estimated_budget", "Unspecified"),
        recommended_service=analysis_data.get("recommended_service", "General Development"),
        summary=analysis_data.get("summary", ""),
        suggested_reply=analysis_data.get("suggested_reply", ""),
        match_reasoning=analysis_data.get("match_reasoning", [])
    )
    db.add(analysis)
    return analysis

def get_leads_for_user(
    db: Session, 
    user_id: int, 
    only_relevant: bool = True, 
    min_score: int = 0, 
    industry: Optional[str] = None, 
    status_filter: Optional[str] = None,
    saved_only: bool = False,
    limit: int = 50
) -> List[LeadAnalysis]:
    query = db.query(LeadAnalysis).filter(LeadAnalysis.user_id == user_id)
    
    if only_relevant:
        query = query.filter(LeadAnalysis.relevant == True)
    if min_score > 0:
        query = query.filter(LeadAnalysis.score >= min_score)
    if industry:
        query = query.filter(LeadAnalysis.industry.ilike(f"%{industry}%"))
    if status_filter:
        query = query.filter(LeadAnalysis.status == status_filter)
    if saved_only:
        query = query.filter(LeadAnalysis.saved == True)
        
    return query.order_by(LeadAnalysis.score.desc()).limit(limit).all()

def update_lead_status(db: Session, post_id: int, user_id: int, status: str) -> Optional[LeadAnalysis]:
    analysis = get_lead_analysis(db, post_id=post_id, user_id=user_id)
    if not analysis:
        return None
    analysis.status = status
    db.commit()
    return analysis

def save_lead_status(db: Session, post_id: int, user_id: int, saved: bool) -> Optional[LeadAnalysis]:
    analysis = get_lead_analysis(db, post_id=post_id, user_id=user_id)
    if not analysis:
        return None
    analysis.saved = saved
    db.commit()
    return analysis

def add_lead_note(db: Session, post_id: int, user_id: int, note_text: str) -> Optional[LeadAnalysis]:
    analysis = get_lead_analysis(db, post_id=post_id, user_id=user_id)
    if not analysis:
        return None
    current_notes = list(analysis.notes or [])
    current_notes.append({
        "text": note_text,
        "timestamp": datetime.datetime.now().isoformat()
    })
    analysis.notes = current_notes
    db.commit()
    return analysis

# --- ADMIN STATS CRUD ---

def get_admin_statistics(db: Session) -> Dict[str, Any]:
    total_users = db.query(User).count()
    total_posts = db.query(RedditPost).count()
    total_matches = db.query(LeadAnalysis).filter(LeadAnalysis.relevant == True).count()
    
    avg_score_row = db.query(func.avg(LeadAnalysis.score)).first()
    avg_score = float(avg_score_row[0]) if avg_score_row and avg_score_row[0] is not None else 0.0
    
    total_analyzed = db.query(LeadAnalysis).count()
    openai_cost = total_analyzed * 0.002
    
    subreddits = db.query(RedditPost.subreddit, func.count(RedditPost.id)).group_by(RedditPost.subreddit).all()
    sub_dist = {row[0]: row[1] for row in subreddits}
    
    return {
        "total_users": total_users,
        "total_posts_collected": total_posts,
        "total_lead_matches": total_matches,
        "average_match_score": round(avg_score, 1),
        "estimated_llm_cost": round(openai_cost, 4),
        "subreddit_distribution": sub_dist
    }
