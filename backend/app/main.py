from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from app.database import engine, Base, get_db
from app.models import RedditPost, LeadAnalysis, UserPreferences
from app.collector import collect_leads
from app.analyzer import analyze_pending_posts
from app.notifier import send_lead_notification
from app.onboarding_service import initialize_onboarding, process_onboarding_turn

# Initialize database tables on startup
Base.metadata.create_all(bind=engine)

app = FastAPI(title="LeadRadar AI Backend")

class OnboardingResponse(BaseModel):
    response: str

@app.get('/')
def home():
    return {
        "message": "Hello! This is Dharanidharan. LeadRadar AI is active."
    }

@app.get('/users')
def users():
    return [
        { "id": 1, "name": "Dharanidharan" },
        { "id": 2, "name": "DD" }
    ]

@app.post('/onboarding/start')
def start_onboarding(db: Session = Depends(get_db)):
    try:
        question = initialize_onboarding(db, user_id=1)
        return {
            "status": "in_progress",
            "question": question,
            "question_count": 1,
            "confidence": 0.0
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to start onboarding: {str(e)}")

@app.post('/onboarding/respond')
def respond_onboarding(data: OnboardingResponse, db: Session = Depends(get_db)):
    try:
        result = process_onboarding_turn(db, user_response=data.response, user_id=1)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to process onboarding response: {str(e)}")

@app.get('/onboarding/status')
def onboarding_status(db: Session = Depends(get_db)):
    prefs = db.query(UserPreferences).filter(UserPreferences.user_id == 1).first()
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

@app.get('/collector/posts')
def get_posts(limit: int = 50, db: Session = Depends(get_db)):
    posts = db.query(RedditPost).order_by(RedditPost.created_utc.desc()).limit(limit).all()
    return posts

@app.post('/leads/analyze')
def trigger_analysis(limit: int = 10, db: Session = Depends(get_db)):
    try:
        results = analyze_pending_posts(db, limit=limit)
        return {
            "status": "success",
            "message": "AI scoring cycle completed",
            "details": results
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")

@app.get('/leads')
def get_leads(only_relevant: bool = True, min_score: int = 0, industry: str = None, limit: int = 50, db: Session = Depends(get_db)):
    query = db.query(RedditPost).join(LeadAnalysis)
    if only_relevant:
        query = query.filter(LeadAnalysis.relevant == True)
    if min_score > 0:
        query = query.filter(LeadAnalysis.score >= min_score)
    if industry:
        query = query.filter(LeadAnalysis.industry.ilike(f"%{industry}%"))
    
    # Order by score descending to return highest quality opportunities first
    leads = query.order_by(LeadAnalysis.score.desc()).limit(limit).all()
    
    results = []
    for post in leads:
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
                "relevant": post.analysis.relevant,
                "score": post.analysis.score,
                "industry": post.analysis.industry,
                "urgency": post.analysis.urgency,
                "intent": post.analysis.intent,
                "estimated_budget": post.analysis.estimated_budget,
                "recommended_service": post.analysis.recommended_service,
                "summary": post.analysis.summary,
                "suggested_reply": post.analysis.suggested_reply,
                "match_reasoning": post.analysis.match_reasoning,
                "analyzed_at": post.analysis.analyzed_at
            }
        })
    return results

@app.get('/leads/{id}')
def get_lead_details(id: int, db: Session = Depends(get_db)):
    post = db.query(RedditPost).filter(RedditPost.id == id).first()
    if not post:
        raise HTTPException(status_code=404, detail="Lead not found")
        
    analysis_data = None
    if post.analysis:
        analysis_data = {
            "relevant": post.analysis.relevant,
            "score": post.analysis.score,
            "industry": post.analysis.industry,
            "urgency": post.analysis.urgency,
            "intent": post.analysis.intent,
            "estimated_budget": post.analysis.estimated_budget,
            "recommended_service": post.analysis.recommended_service,
            "summary": post.analysis.summary,
            "suggested_reply": post.analysis.suggested_reply,
            "match_reasoning": post.analysis.match_reasoning,
            "analyzed_at": post.analysis.analyzed_at
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
