from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel, EmailStr
from typing import List, Optional
import httpx
import logging
import datetime

from app.database import engine, Base, get_db
from app.models import User, RedditPost, LeadAnalysis, UserPreferences
from app.collector import collect_leads
from app.analyzer import analyze_pending_posts
from app.notifier import send_lead_notification
from app.onboarding_service import initialize_onboarding, process_onboarding_turn
from app.auth_service import (
    get_password_hash,
    verify_password,
    create_access_token,
    get_current_user,
    get_current_admin
)
from app.config import settings

# Initialize database tables
Base.metadata.create_all(bind=engine)

app = FastAPI(title="LeadRadar AI Backend")

# Enable CORS for frontend requests
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # For production, we can configure this to settings.FRONTEND_URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

logger = logging.getLogger(__name__)

# --- REQUEST/RESPONSE SCHEMAS ---

class UserRegister(BaseModel):
    email: EmailStr
    password: str
    full_name: Optional[str] = None

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class Token(BaseModel):
    access_token: str
    token_type: str
    is_admin: bool

class OnboardingResponse(BaseModel):
    response: str

class StatusUpdate(BaseModel):
    status: str  # New, Replied, Interested, Won, Lost

class NoteCreate(BaseModel):
    text: str

class MonitoredSubredditsUpdate(BaseModel):
    subreddits: str

class PromptsUpdate(BaseModel):
    analyzer_instructions: Optional[str] = None
    onboarding_instructions: Optional[str] = None

# --- AUTHENTICATION ENDPOINTS ---

@app.post('/auth/register', response_model=Token)
def register(data: UserRegister, db: Session = Depends(get_db)):
    # Check if email is already taken
    existing_user = db.query(User).filter(User.email == data.email).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email address is already registered."
        )
    
    # Hash password and create user
    hashed_password = get_password_hash(data.password)
    user = User(
        email=data.email,
        hashed_password=hashed_password,
        full_name=data.full_name,
        is_admin=False
    )
    db.add(user)
    db.flush()
    
    # Initialize user preferences
    prefs = UserPreferences(
        user_id=user.id,
        onboarding_status="not_started",
        onboarding_history=[],
        question_count=0,
        confidence=0.0,
        profile_json=None
    )
    db.add(prefs)
    db.commit()
    
    access_token = create_access_token(data={"sub": user.email})
    return {"access_token": access_token, "token_type": "bearer", "is_admin": user.is_admin}

@app.post('/auth/login', response_model=Token)
def login(data: UserLogin, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == data.email).first()
    if not user or not verify_password(data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    access_token = create_access_token(data={"sub": user.email})
    return {"access_token": access_token, "token_type": "bearer", "is_admin": user.is_admin}

@app.get('/auth/me')
def get_me(current_user: User = Depends(get_current_user)):
    return {
        "id": current_user.id,
        "email": current_user.email,
        "full_name": current_user.full_name,
        "is_admin": current_user.is_admin,
        "created_at": current_user.created_at
    }

@app.get('/auth/google')
def google_login():
    client_id = settings.GOOGLE_CLIENT_ID
    redirect_uri = settings.GOOGLE_REDIRECT_URI
    if not client_id:
        raise HTTPException(
            status_code=400, 
            detail="Google Client ID is not configured in .env."
        )
    
    scope = "openid email profile"
    auth_url = (
        f"https://accounts.google.com/o/oauth2/v2/auth?"
        f"client_id={client_id}&"
        f"redirect_uri={redirect_uri}&"
        f"response_type=code&"
        f"scope={scope}"
    )
    return {"url": auth_url}

@app.get('/auth/google/callback')
async def google_callback(code: str = None, db: Session = Depends(get_db)):
    if not code:
        raise HTTPException(status_code=400, detail="OAuth authorization code not provided.")
    
    client_id = settings.GOOGLE_CLIENT_ID
    client_secret = settings.GOOGLE_CLIENT_SECRET
    redirect_uri = settings.GOOGLE_REDIRECT_URI
    
    token_url = "https://oauth2.googleapis.com/token"
    data = {
        "code": code,
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code"
    }
    
    try:
        async with httpx.AsyncClient() as client:
            token_response = await client.post(token_url, data=data, timeout=10.0)
            token_response.raise_for_status()
            token_json = token_response.json()
            access_token = token_json.get("access_token")
            
            userinfo_url = "https://www.googleapis.com/oauth2/v3/userinfo"
            headers = {"Authorization": f"Bearer {access_token}"}
            userinfo_response = await client.get(userinfo_url, headers=headers, timeout=10.0)
            userinfo_response.raise_for_status()
            user_info = userinfo_response.json()
            
        email = user_info.get("email")
        full_name = user_info.get("name", "")
        
        if not email:
            raise HTTPException(status_code=400, detail="Google authentication did not provide an email.")
            
        # Find or create Google authenticated user
        user = db.query(User).filter(User.email == email).first()
        if not user:
            import secrets
            random_pw = secrets.token_hex(16)
            hashed_pw = get_password_hash(random_pw)
            user = User(
                email=email,
                hashed_password=hashed_pw,
                full_name=full_name,
                is_admin=False
            )
            db.add(user)
            db.flush()
            
            # Create user preferences
            prefs = UserPreferences(
                user_id=user.id,
                onboarding_status="not_started",
                onboarding_history=[],
                question_count=0,
                confidence=0.0,
                profile_json=None
            )
            db.add(prefs)
            db.commit()
            
        jwt_token = create_access_token(data={"sub": user.email})
        
        # Redirect to frontend callback page
        return RedirectResponse(url=f"{settings.FRONTEND_URL}/auth/callback?token={jwt_token}")
        
    except Exception as e:
        logger.error(f"Google OAuth Callback failed: {e}", exc_info=True)
        return RedirectResponse(url=f"{settings.FRONTEND_URL}/login?error=oauth_failed")

# --- CONVERSATIONAL ONBOARDING ENDPOINTS ---

@app.post('/onboarding/start')
def start_onboarding(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        question = initialize_onboarding(db, user_id=current_user.id)
        return {
            "status": "in_progress",
            "question": question,
            "question_count": 1,
            "confidence": 0.0
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to start onboarding: {str(e)}")

@app.post('/onboarding/respond')
def respond_onboarding(data: OnboardingResponse, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        result = process_onboarding_turn(db, user_response=data.response, user_id=current_user.id)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to process onboarding response: {str(e)}")

@app.get('/onboarding/status')
def onboarding_status(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    prefs = db.query(UserPreferences).filter(UserPreferences.user_id == current_user.id).first()
    if not prefs:
        return {
            "status": "not_started",
            "history": [],
            "question_count": 0,
            "confidence": 0.0,
            "profile": None
        }
    return {
        "status": prefs.onboarding_status,
        "history": prefs.onboarding_history,
        "question_count": prefs.question_count,
        "confidence": prefs.confidence,
        "profile": prefs.profile_json
    }

# --- LEADS & CRM WORKFLOW ENDPOINTS ---

@app.get('/leads')
def get_leads(
    only_relevant: bool = True, 
    min_score: int = 0, 
    industry: str = None, 
    status_filter: str = None,
    saved_only: bool = False,
    limit: int = 50, 
    current_user: User = Depends(get_current_user), 
    db: Session = Depends(get_db)
):
    query = db.query(LeadAnalysis).filter(LeadAnalysis.user_id == current_user.id)
    
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
        
    leads = query.order_by(LeadAnalysis.score.desc()).limit(limit).all()
    
    results = []
    for analysis in leads:
        post = analysis.post
        results.append({
            "id": post.id,
            "reddit_id": post.reddit_id,
            "title": post.title,
            "content": post.content,
            "author": post.author,
            "subreddit": post.subreddit,
            "url": post.url,
            "created_utc": post.created_utc,
            "collected_at": post.collected_at,
            "analysis": {
                "relevant": analysis.relevant,
                "score": analysis.score,
                "industry": analysis.industry,
                "urgency": analysis.urgency,
                "intent": analysis.intent,
                "estimated_budget": analysis.estimated_budget,
                "recommended_service": analysis.recommended_service,
                "summary": analysis.summary,
                "suggested_reply": analysis.suggested_reply,
                "match_reasoning": analysis.match_reasoning,
                "status": analysis.status,
                "saved": analysis.saved,
                "notes": analysis.notes,
                "analyzed_at": analysis.analyzed_at
            }
        })
    return results

@app.get('/leads/{id}')
def get_lead_details(id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    post = db.query(RedditPost).filter(RedditPost.id == id).first()
    if not post:
        raise HTTPException(status_code=404, detail="Lead not found")
        
    analysis = db.query(LeadAnalysis).filter(
        LeadAnalysis.post_id == id,
        LeadAnalysis.user_id == current_user.id
    ).first()
    
    analysis_data = None
    if analysis:
        analysis_data = {
            "relevant": analysis.relevant,
            "score": analysis.score,
            "industry": analysis.industry,
            "urgency": analysis.urgency,
            "intent": analysis.intent,
            "estimated_budget": analysis.estimated_budget,
            "recommended_service": analysis.recommended_service,
            "summary": analysis.summary,
            "suggested_reply": analysis.suggested_reply,
            "match_reasoning": analysis.match_reasoning,
            "status": analysis.status,
            "saved": analysis.saved,
            "notes": analysis.notes,
            "analyzed_at": analysis.analyzed_at
        }
        
    return {
        "id": post.id,
        "reddit_id": post.reddit_id,
        "title": post.title,
        "content": post.content,
        "author": post.author,
        "subreddit": post.subreddit,
        "url": post.url,
        "created_utc": post.created_utc,
        "collected_at": post.collected_at,
        "analysis": analysis_data
    }

@app.patch('/leads/{id}/status')
def update_lead_status(id: int, data: StatusUpdate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    analysis = db.query(LeadAnalysis).filter(
        LeadAnalysis.post_id == id,
        LeadAnalysis.user_id == current_user.id
    ).first()
    
    if not analysis:
        raise HTTPException(status_code=404, detail="Lead analysis record not found.")
        
    analysis.status = data.status
    db.commit()
    return {"status": "success", "message": f"Lead status updated to {data.status}"}

@app.post('/leads/{id}/notes')
def add_lead_note(id: int, data: NoteCreate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    analysis = db.query(LeadAnalysis).filter(
        LeadAnalysis.post_id == id,
        LeadAnalysis.user_id == current_user.id
    ).first()
    
    if not analysis:
        raise HTTPException(status_code=404, detail="Lead analysis record not found.")
        
    current_notes = list(analysis.notes or [])
    current_notes.append({
        "text": data.text,
        "timestamp": datetime.datetime.now().isoformat()
    })
    analysis.notes = current_notes
    db.commit()
    return {"status": "success", "notes": analysis.notes}

@app.post('/leads/{id}/save')
def save_lead(id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    analysis = db.query(LeadAnalysis).filter(
        LeadAnalysis.post_id == id,
        LeadAnalysis.user_id == current_user.id
    ).first()
    
    if not analysis:
        raise HTTPException(status_code=404, detail="Lead analysis record not found.")
        
    analysis.saved = True
    db.commit()
    return {"status": "success", "saved": True}

@app.delete('/leads/{id}/save')
def unsave_lead(id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    analysis = db.query(LeadAnalysis).filter(
        LeadAnalysis.post_id == id,
        LeadAnalysis.user_id == current_user.id
    ).first()
    
    if not analysis:
        raise HTTPException(status_code=404, detail="Lead analysis record not found.")
        
    analysis.saved = False
    db.commit()
    return {"status": "success", "saved": False}

# --- SYSTEM TRIGGERS (USER-LEVEL ACCESS) ---

@app.post('/collector/trigger')
def trigger_collector(db: Session = Depends(get_db)):
    try:
        results = collect_leads(db)
        return {
            "status": "success",
            "message": "Reddit collection cycle completed",
            "details": results
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Collector failed: {str(e)}")

@app.post('/leads/analyze')
def trigger_user_analysis(limit: int = 10, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        results = analyze_pending_posts(db, user_id=current_user.id, limit=limit)
        return {
            "status": "success",
            "message": "AI matching analysis complete",
            "details": results
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Matching analysis failed: {str(e)}")

@app.post('/notifications/test')
def test_notification():
    success = send_lead_notification(
        score=95,
        subreddit="SaaS",
        intent="Website Development & Online Ordering System",
        budget="$5000",
        service="Web Development",
        summary="Restaurant owner looking to rebuild their website with custom online ordering. High intent, ready to hire.",
        reply="Hi! I saw you are looking to build a website with online ordering. I build custom web applications and would love to help you with this project.",
        url="https://reddit.com/r/SaaS/dummy_post_id"
    )
    if not success:
        raise HTTPException(
            status_code=400, 
            detail="Failed to send test notification. Please verify your TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in .env."
        )
    return {
        "status": "success",
        "message": "Test Telegram notification sent successfully"
    }

# --- SUPERADMIN ENDPOINTS (ADMIN ROLE-RESTRICTED) ---

@app.get('/admin/stats')
def get_admin_stats(current_admin: User = Depends(get_current_admin), db: Session = Depends(get_db)):
    total_users = db.query(User).count()
    total_posts = db.query(RedditPost).count()
    total_matches = db.query(LeadAnalysis).filter(LeadAnalysis.relevant == True).count()
    
    # Simple average score calculation
    from sqlalchemy import func
    avg_score_row = db.query(func.avg(LeadAnalysis.score)).first()
    avg_score = float(avg_score_row[0]) if avg_score_row and avg_score_row[0] is not None else 0.0
    
    # Mocking cost tracking: $0.002 per analysis
    total_analyzed = db.query(LeadAnalysis).count()
    openai_cost = total_analyzed * 0.002
    
    # Subreddit distribution count
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

@app.get('/admin/users')
def get_admin_users(current_admin: User = Depends(get_current_admin), db: Session = Depends(get_db)):
    users = db.query(User).all()
    results = []
    for user in users:
        prefs = db.query(UserPreferences).filter(UserPreferences.user_id == user.id).first()
        results.append({
            "id": user.id,
            "email": user.email,
            "full_name": user.full_name,
            "is_admin": user.is_admin,
            "created_at": user.created_at,
            "onboarding": {
                "status": prefs.onboarding_status if prefs else "not_started",
                "question_count": prefs.question_count if prefs else 0,
                "confidence": prefs.confidence if prefs else 0.0,
                "profile": prefs.profile_json if prefs else None
            }
        })
    return results

@app.get('/admin/config')
def get_admin_config(current_admin: User = Depends(get_current_admin)):
    return {
        "monitored_subreddits": settings.MONITORED_SUBREDDITS,
        "min_notification_score": settings.MIN_NOTIFICATION_SCORE,
        "poll_interval_seconds": settings.POLL_INTERVAL_SECONDS
    }

@app.put('/admin/config')
def update_admin_config(data: MonitoredSubredditsUpdate, current_admin: User = Depends(get_current_admin)):
    settings.MONITORED_SUBREDDITS = data.subreddits
    return {"status": "success", "monitored_subreddits": settings.MONITORED_SUBREDDITS}

@app.post('/admin/trigger/collect')
def admin_trigger_collect(current_admin: User = Depends(get_current_admin), db: Session = Depends(get_db)):
    results = collect_leads(db)
    return {"status": "success", "results": results}

@app.post('/admin/trigger/analyze')
def admin_trigger_analyze(limit: int = 15, current_admin: User = Depends(get_current_admin), db: Session = Depends(get_db)):
    # Trigger matching analysis for all users who completed onboarding
    active_users = db.query(UserPreferences).filter(UserPreferences.onboarding_status == "completed").all()
    results = {}
    for user_pref in active_users:
        res = analyze_pending_posts(db, user_id=user_pref.user_id, limit=limit)
        results[user_pref.user_id] = res
    return {"status": "success", "details": results}

@app.get('/admin/home')
def admin_home():
    return {"message": "Welcome to LeadRadar AI Superadmin API Dashboard"}