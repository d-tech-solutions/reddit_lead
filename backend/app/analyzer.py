import logging
import time
from sqlalchemy.orm import Session
from app.config import settings
from app.models import RedditPost, LeadAnalysis, UserPreferences
from app.ai_service import analyze_post
from app.notifier import send_lead_notification

logger = logging.getLogger(__name__)

def analyze_pending_posts(db: Session, limit: int = 10) -> dict:
    """Find Reddit posts without analysis, qualify them against the search intent profile, and store them."""
    # Retrieve user search intent profile
    prefs = db.query(UserPreferences).filter(UserPreferences.user_id == 1).first()
    
    if not prefs or prefs.onboarding_status != "completed" or not prefs.profile_json:
        logger.warning("No completed search intent profile found for user 1. Skipping analysis.")
        return {
            "processed": 0,
            "successful": 0,
            "warning": "Search intent profile is not yet set up. Please complete setup in Settings/Dashboard."
        }
        
    profile = prefs.profile_json

    # Find posts that do not have an associated LeadAnalysis entry
    pending_posts = (
        db.query(RedditPost)
        .outerjoin(LeadAnalysis)
        .filter(LeadAnalysis.id == None)
        .limit(limit)
        .all()
    )
    
    total_found = len(pending_posts)
    if total_found == 0:
        logger.info("No pending Reddit posts found for AI analysis.")
        return {"processed": 0, "successful": 0}
        
    logger.info(f"Found {total_found} pending posts to analyze (limit={limit}) using profile. Starting analysis...")
    
    successful_count = 0
    for post in pending_posts:
        try:
            logger.info(f"Analyzing post ID={post.id} (reddit_id={post.reddit_id}) title='{post.title[:30]}...'")
            analysis_result = analyze_post(post.title, post.content, search_intent_profile=profile)
            
            # Persist the analysis
            db_analysis = LeadAnalysis(
                post_id=post.id,
                relevant=analysis_result.get("relevant", False),
                score=analysis_result.get("score", 0),
                industry=analysis_result.get("industry", "General"),
                urgency=analysis_result.get("urgency", "Low"),
                intent=analysis_result.get("intent", "Unknown"),
                estimated_budget=analysis_result.get("estimated_budget", "Unspecified"),
                recommended_service=analysis_result.get("recommended_service", "General Development"),
                summary=analysis_result.get("summary", ""),
                suggested_reply=analysis_result.get("suggested_reply", ""),
                match_reasoning=analysis_result.get("match_reasoning", [])
            )
            db.add(db_analysis)
            db.commit()
            successful_count += 1
            
            # Send notification if the lead is relevant and score matches or exceeds threshold
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
            logger.error(f"Error during AI analysis for post ID={post.id}: {e}", exc_info=True)
            
    logger.info(f"Analysis complete. Processed {total_found} posts, successfully scored and saved {successful_count} leads.")
    return {
        "processed": total_found,
        "successful": successful_count
    }
