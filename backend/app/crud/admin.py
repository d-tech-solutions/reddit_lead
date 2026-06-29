from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import Dict, Any
from app.models import User, RedditPost, LeadAnalysis

def get_admin_statistics(db: Session) -> Dict[str, Any]:
    """
    Calculate and compile global application-wide metrics for the superadmin dashboard.
    Computes total users, posts collected, relevant lead matches, average scores,
    approximate API cost metrics, and subreddit distribution groupings.
    
    Args:
        db (Session): Active SQLAlchemy database session.
        
    Returns:
        Dict[str, Any]: A dictionary containing calculated statistical values:
            - "total_users" (int): Number of registered user accounts.
            - "total_posts_collected" (int): Total ingested posts from Reddit RSS.
            - "total_lead_matches" (int): Number of leads qualified as relevant.
            - "average_match_score" (float): Average match score of processed leads.
            - "estimated_llm_cost" (float): Approximate API spend estimation based on usage.
            - "subreddit_distribution" (Dict[str, int]): Count of posts grouped by subreddit.
    """
    total_users = db.query(User).count()
    total_posts = db.query(RedditPost).count()
    total_matches = db.query(LeadAnalysis).filter(LeadAnalysis.relevant == True).count()
    
    avg_score_row = db.query(func.avg(LeadAnalysis.score)).first()
    avg_score = float(avg_score_row[0]) if avg_score_row and avg_score_row[0] is not None else 0.0
    
    total_analyzed = db.query(LeadAnalysis).count()
    openai_cost = total_analyzed * 0.002
    
    subreddits = db.query(RedditPost.subreddit, func.count(RedditPost.id)).group_by(RedditPost.subreddit).all()
    sub_dist = {row[0]: row[1] for row in subreddits}
    
    return {
        "total_users": total_users,
        "total_posts_collected": total_posts,
        "total_lead_matches": total_matches,
        "average_match_score": round(avg_score, 1),
        "estimated_llm_cost": round(openai_cost, 4),
        "subreddit_distribution": sub_dist
    }
