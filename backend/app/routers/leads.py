from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Optional

from app.database import get_db
from app.models import User
from app.schemas import StatusUpdate, NoteCreate
from app.auth_service import get_current_user
from app import crud

router = APIRouter(prefix="/leads", tags=["Leads & CRM"])

@router.get('')
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
    leads = crud.get_leads_for_user(
        db,
        user_id=current_user.id,
        only_relevant=only_relevant,
        min_score=min_score,
        industry=industry,
        status_filter=status_filter,
        saved_only=saved_only,
        limit=limit
    )
    
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

@router.get('/{id}')
def get_lead_details(id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    post = crud.get_post_by_id(db, post_id=id)
    if not post:
        raise HTTPException(status_code=404, detail="Lead not found")
        
    analysis = crud.get_lead_analysis(db, post_id=id, user_id=current_user.id)
    
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

@router.patch('/{id}/status')
def update_lead_status(id: int, data: StatusUpdate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    analysis = crud.update_lead_status(db, post_id=id, user_id=current_user.id, status=data.status)
    if not analysis:
        raise HTTPException(status_code=404, detail="Lead analysis record not found.")
    return {"status": "success", "message": f"Lead status updated to {data.status}"}

@router.post('/{id}/notes')
def add_lead_note(id: int, data: NoteCreate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    analysis = crud.add_lead_note(db, post_id=id, user_id=current_user.id, note_text=data.text)
    if not analysis:
        raise HTTPException(status_code=404, detail="Lead analysis record not found.")
    return {"status": "success", "notes": analysis.notes}

@router.post('/{id}/save')
def save_lead(id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    analysis = crud.save_lead_status(db, post_id=id, user_id=current_user.id, saved=True)
    if not analysis:
        raise HTTPException(status_code=404, detail="Lead analysis record not found.")
    return {"status": "success", "saved": True}

@router.delete('/{id}/save')
def unsave_lead(id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    analysis = crud.save_lead_status(db, post_id=id, user_id=current_user.id, saved=False)
    if not analysis:
        raise HTTPException(status_code=404, detail="Lead analysis record not found.")
    return {"status": "success", "saved": False}
