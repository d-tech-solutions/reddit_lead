from sqlalchemy.orm import Session
from typing import List, Optional
import datetime
from app.models import LeadAnalysis

def get_lead_analysis(db: Session, post_id: int, user_id: int) -> Optional[LeadAnalysis]:
    """
    Retrieve a specific LeadAnalysis record based on a composite key of post ID and user ID.
    
    Args:
        db (Session): Active SQLAlchemy database session.
        post_id (int): Primary key ID of the Reddit post.
        user_id (int): Primary key ID of the user who performed the analysis.
        
    Returns:
        Optional[LeadAnalysis]: The LeadAnalysis model instance if found, otherwise None.
    """
    return db.query(LeadAnalysis).filter(
        LeadAnalysis.post_id == post_id,
        LeadAnalysis.user_id == user_id
    ).first()

def create_lead_analysis(db: Session, analysis_data: dict) -> LeadAnalysis:
    """
    Insert a new AI-evaluated LeadAnalysis qualification score and summary details.
    
    Args:
        db (Session): Active SQLAlchemy database session.
        analysis_data (dict): Dictionary with analysis fields:
            - "post_id" (int): Foreign key referencing target RedditPost.
            - "user_id" (int): Foreign key referencing user preferences configuration.
            - "relevant" (bool): Evaluated matching status.
            - "score" (int): Evaluated match strength (0 to 100).
            - "industry" (Optional[str]): Identified business sector.
            - "urgency" (Optional[str]): Identified pipeline urgency.
            - "intent" (Optional[str]): Main intent tags.
            - "estimated_budget" (Optional[str]): Projected project valuation.
            - "recommended_service" (Optional[str]): Suggested matches from user services.
            - "summary" (Optional[str]): Brief 1-2 sentence overview of requirements.
            - "suggested_reply" (Optional[str]): AI generated context pitch reply.
            - "match_reasoning" (Optional[list]): Bulleted reason indicators list.
            
    Returns:
        LeadAnalysis: The created LeadAnalysis database instance.
    """
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
    """
    Fetch, filter, and prioritize lead qualifications matching a user's CRM parameters.
    
    Args:
        db (Session): Active SQLAlchemy database session.
        user_id (int): Primary key ID of the user requesting leads.
        only_relevant (bool): Filter to only return matches evaluated as relevant.
        min_score (int): Minimum match score threshold to return.
        industry (Optional[str]): Filter matching industry strings (case-insensitive).
        status_filter (Optional[str]): Filter matching pipeline stages ("New", "Replied", "Interested", etc.).
        saved_only (bool): Filter to only return bookmarked/saved items.
        limit (int): Maximum number of entries to return.
        
    Returns:
        List[LeadAnalysis]: A prioritized list of matched LeadAnalysis records sorted by score descending.
    """
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
    """
    Change the CRM status/pipeline phase of a lead.
    
    Args:
        db (Session): Active SQLAlchemy database session.
        post_id (int): Primary key ID of the post.
        user_id (int): Primary key ID of the user.
        status (str): New pipeline stage ("New", "Replied", "Interested", "Won", "Lost").
        
    Returns:
        Optional[LeadAnalysis]: Updated LeadAnalysis instance, or None if not found.
    """
    analysis = get_lead_analysis(db, post_id=post_id, user_id=user_id)
    if not analysis:
        return None
    analysis.status = status
    db.commit()
    return analysis

def save_lead_status(db: Session, post_id: int, user_id: int, saved: bool) -> Optional[LeadAnalysis]:
    """
    Toggle the saved/bookmarked state of a lead.
    
    Args:
        db (Session): Active SQLAlchemy database session.
        post_id (int): Primary key ID of the post.
        user_id (int): Primary key ID of the user.
        saved (bool): Target bookmark state.
        
    Returns:
        Optional[LeadAnalysis]: Updated LeadAnalysis instance, or None if not found.
    """
    analysis = get_lead_analysis(db, post_id=post_id, user_id=user_id)
    if not analysis:
        return None
    analysis.saved = saved
    db.commit()
    return analysis

def add_lead_note(db: Session, post_id: int, user_id: int, note_text: str) -> Optional[LeadAnalysis]:
    """
    Append an administrative note with a timestamp to the lead's notes JSON log.
    
    Args:
        db (Session): Active SQLAlchemy database session.
        post_id (int): Primary key ID of the post.
        user_id (int): Primary key ID of the user.
        note_text (str): Message text to record.
        
    Returns:
        Optional[LeadAnalysis]: Updated LeadAnalysis instance, or None if not found.
    """
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
