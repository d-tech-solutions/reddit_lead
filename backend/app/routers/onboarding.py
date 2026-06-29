from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.schemas import OnboardingResponse
from app.auth_service import get_current_user
from app.onboarding_service import initialize_onboarding, process_onboarding_turn
from app import crud

router = APIRouter(prefix="/onboarding", tags=["Onboarding"])

@router.post('/start')
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

@router.post('/respond')
def respond_onboarding(data: OnboardingResponse, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        result = process_onboarding_turn(db, user_response=data.response, user_id=current_user.id)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to process onboarding response: {str(e)}")

@router.get('/status')
def onboarding_status(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    prefs = crud.get_user_preferences(db, user_id=current_user.id)
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
