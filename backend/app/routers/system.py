from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.auth_service import get_current_user
from app.collector import collect_leads
from app.analyzer import analyze_pending_posts
from app.notifier import send_lead_notification

router = APIRouter(tags=["System Triggers"])

@router.post('/collector/trigger')
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

@router.post('/leads/analyze')
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

@router.post('/notifications/test')
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
