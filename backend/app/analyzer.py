import logging
from sqlalchemy.orm import Session
from app.models import RedditPost, LeadAnalysis
from app.ai_service import analyze_post

logger = logging.getLogger(__name__)

def analyze_pending_posts(db: Session, limit: int = 10) -> dict:
    """Find Reddit posts without analysis, fetch their scores from AI, and store them."""
    # Find posts that do not have an associated LeadAnalysis entry
    # Using an outer join to identify posts where LeadAnalysis.id is NULL
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
        
    logger.info(f"Found {total_found} pending posts to analyze (limit={limit}). Starting analysis...")
    
    successful_count = 0
    for post in pending_posts:
        try:
            logger.info(f"Analyzing post ID={post.id} (reddit_id={post.reddit_id}) title='{post.title[:30]}...'")
            analysis_result = analyze_post(post.title, post.content)
            
            # Persist the analysis
            db_analysis = LeadAnalysis(
                post_id=post.id,
                score=analysis_result.get("score", 0),
                industry=analysis_result.get("industry", "General"),
                urgency=analysis_result.get("urgency", "Low"),
                intent=analysis_result.get("intent", "Unknown"),
                estimated_budget=analysis_result.get("estimated_budget", "Unspecified"),
                recommended_service=analysis_result.get("recommended_service", "General Development"),
                summary=analysis_result.get("summary", ""),
                suggested_reply=analysis_result.get("suggested_reply", "")
            )
            db.add(db_analysis)
            db.commit()
            successful_count += 1
            
        except Exception as e:
            db.rollback()
            logger.error(f"Error during AI analysis for post ID={post.id}: {e}", exc_info=True)
            
    logger.info(f"Analysis complete. Processed {total_found} posts, successfully scored and saved {successful_count} leads.")
    return {
        "processed": total_found,
        "successful": successful_count
    }
