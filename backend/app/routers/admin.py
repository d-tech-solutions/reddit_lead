from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.schemas import MonitoredSubredditsUpdate
from app.auth_service import get_current_admin
from app.config import settings
from app import crud
from app.tasks import fetch_and_match_leads_task, analyze_user_pending_leads_task

router = APIRouter(prefix="/admin", tags=["Superadmin"])

@router.get('/stats')
def get_admin_stats(current_admin: User = Depends(get_current_admin), db: Session = Depends(get_db)):
    return crud.get_admin_statistics(db)

@router.get('/users')
def get_admin_users(current_admin: User = Depends(get_current_admin), db: Session = Depends(get_db)):
    users = crud.get_all_users(db)
    results = []
    for user in users:
        prefs = crud.get_user_preferences(db, user_id=user.id)
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

@router.get('/config')
def get_admin_config(current_admin: User = Depends(get_current_admin)):
    return {
        "monitored_subreddits": settings.MONITORED_SUBREDDITS,
        "min_notification_score": settings.MIN_NOTIFICATION_SCORE,
        "poll_interval_seconds": settings.POLL_INTERVAL_SECONDS
    }

@router.put('/config')
def update_admin_config(data: MonitoredSubredditsUpdate, current_admin: User = Depends(get_current_admin)):
    settings.MONITORED_SUBREDDITS = data.subreddits
    return {"status": "success", "monitored_subreddits": settings.MONITORED_SUBREDDITS}

@router.post('/trigger/collect')
def admin_trigger_collect(current_admin: User = Depends(get_current_admin)):
    task = fetch_and_match_leads_task.delay()
    return {"status": "success", "task_id": task.id}

@router.post('/trigger/analyze')
def admin_trigger_analyze(limit: int = 15, current_admin: User = Depends(get_current_admin), db: Session = Depends(get_db)):
    # Trigger matching analysis for all users who completed onboarding
    from app.models import UserPreferences
    active_users = db.query(UserPreferences).filter(UserPreferences.onboarding_status == "completed").all()
    task_ids = {}
    for user_pref in active_users:
        task = analyze_user_pending_leads_task.delay(user_pref.user_id, limit)
        task_ids[user_pref.user_id] = task.id
    return {"status": "success", "task_ids": task_ids}

@router.get('/home')
def admin_home():
    return {"message": "Welcome to LeadRadar AI Superadmin API Dashboard"}
