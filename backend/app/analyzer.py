import logging
import time
from sqlalchemy.orm import Session
from app.config import settings
from app import crud
from app.ai_service import analyze_post
from app.notifier import send_lead_notification

logger = logging.getLogger(__name__)

def analyze_pending_posts(db: Session, user_id: int, limit: int = 10) -> dict:
    # Retrieve user intent profile
    prefs = crud.get_user_preferences(db, user_id=user_id)
    if not prefs or prefs.onboarding_status != "completed" or not prefs.profile_json:
        logger.warning(f"User ID={user_id} has not completed onboarding. Skipping analysis.")
        return {"processed": 0, "successful": 0}
        
    search_intent_profile = prefs.profile_json

    # Find posts that do not have an associated LeadAnalysis entry for this specific user
    pending_posts = crud.get_pending_posts_for_user(db, user_id=user_id, limit=limit)

    
    total_found = len(pending_posts)
    if total_found == 0:
        logger.info(f"No pending Reddit posts found for AI analysis for user ID={user_id}.")
        return {"processed": 0, "successful": 0}
        
    logger.info(f"Found {total_found} pending posts to analyze for user ID={user_id} (limit={limit}). Starting analysis...")
    
    successful_count = 0
    for post in pending_posts:
        try:
            logger.info(f"Analyzing post ID={post.id} (reddit_id={post.reddit_id}) title='{post.title[:30]}...' for user ID={user_id}")
            analysis_result = analyze_post(post.title, post.content, search_intent_profile=search_intent_profile)
            
            # Persist the user-specific analysis
            db_analysis = crud.create_lead_analysis(db, {
                "post_id": post.id,
                "user_id": user_id,
                "relevant": analysis_result.get("relevant", False),
                "score": analysis_result.get("score", 0),
                "industry": analysis_result.get("industry", "General"),
                "urgency": analysis_result.get("urgency", "Low"),
                "intent": analysis_result.get("intent", "Unknown"),
                "estimated_budget": analysis_result.get("estimated_budget", "Unspecified"),
                "recommended_service": analysis_result.get("recommended_service", "General Development"),
                "summary": analysis_result.get("summary", ""),
                "suggested_reply": analysis_result.get("suggested_reply", ""),
                "match_reasoning": analysis_result.get("match_reasoning", [])
            })
            db.commit()
            successful_count += 1
            
            # Send notification if score matches or exceeds configured threshold and is relevant
            if db_analysis.relevant and db_analysis.score >= settings.MIN_NOTIFICATION_SCORE:
                try:
                    send_lead_notification(
                        score=db_analysis.score,
                        subreddit=post.subreddit,
                        intent=db_analysis.intent,
                        budget=db_analysis.estimated_budget,
                        service=db_analysis.recommended_service,
                        summary=db_analysis.summary,
                        reply=db_analysis.suggested_reply,
                        url=post.url
                    )
                except Exception as notify_err:
                    logger.error(f"Error sending Telegram notification for post ID={post.id}: {notify_err}", exc_info=True)
            
            # Rate-limiting delay between requests
            time.sleep(1.0)
            
        except Exception as e:
            db.rollback()
            logger.error(f"Error during AI analysis for post ID={post.id} and user ID={user_id}: {e}", exc_info=True)
            
    logger.info(f"Analysis complete. Processed {total_found} posts, successfully scored and saved {successful_count} leads for user ID={user_id}.")
    return {
        "processed": total_found,
        "successful": successful_count
    }
