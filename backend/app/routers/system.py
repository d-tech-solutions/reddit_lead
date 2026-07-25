from fastapi import APIRouter, Depends, HTTPException
from app.models import User
from app.auth_service import get_current_user
from app.notifier import send_lead_notification
from app.tasks import fetch_and_match_leads_task, analyze_user_pending_leads_task

router = APIRouter(tags=["System Triggers"])

@router.post('/collector/trigger')
def trigger_collector():
    try:
        task = fetch_and_match_leads_task.delay()
        return {
            "status": "success",
            "message": "Reddit background collection and matching task enqueued",
            "task_id": task.id
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to enqueue collector task: {str(e)}")

@router.post('/leads/analyze')
def trigger_user_analysis(limit: int = 10, current_user: User = Depends(get_current_user)):
    try:
        task = analyze_user_pending_leads_task.delay(current_user.id, limit)
        return {
            "status": "success",
            "message": "AI background matching analysis task enqueued",
            "task_id": task.id
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to enqueue analysis task: {str(e)}")

@router.get('/tasks/{task_id}')
def get_task_status(task_id: str):
    from celery.result import AsyncResult
    from app.celery_app import celery_app
    try:
        result = AsyncResult(task_id, app=celery_app)
        return {
            "task_id": task_id,
            "status": result.status,
            "result": result.result if result.ready() else None
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to query task status: {str(e)}")

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
