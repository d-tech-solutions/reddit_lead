import logging
from app.celery_app import celery_app
from app.database import SessionLocal
from app.collector import collect_leads
from app.analyzer import match_post_to_users_pipeline, analyze_pending_posts

logger = logging.getLogger(__name__)

@celery_app.task(name="app.tasks.fetch_and_match_leads_task")
def fetch_and_match_leads_task() -> dict:
    """
    Background job to pull new Reddit posts from configured subreddits
    and run the matching pipeline for every newly saved post.
    """
    logger.info("Executing background task fetch_and_match_leads_task...")
    db = SessionLocal()
    try:
        # 1. Ingest posts
        results = collect_leads(db)
        new_posts = results.get("posts", [])
        logger.info(f"Ingested {len(new_posts)} new posts. Running matching pipeline...")
        
        # 2. Match newly enqueued posts against active user profiles
        matched_users_total = 0
        for post in new_posts:
            try:
                match_results = match_post_to_users_pipeline(db, post.id)
                matched_users_total += match_results.get("matched_users", 0)
            except Exception as match_err:
                logger.error(f"Error matching post ID={post.id} inside celery task: {match_err}", exc_info=True)
                
        return {
            "fetched": results.get("fetched", 0),
            "saved": results.get("saved", 0),
            "matched_users": matched_users_total
        }
    except Exception as e:
        logger.error(f"fetch_and_match_leads_task failed: {e}", exc_info=True)
        raise e
    finally:
        db.close()

@celery_app.task(name="app.tasks.analyze_user_pending_leads_task")
def analyze_user_pending_leads_task(user_id: int, limit: int = 15) -> dict:
    """
    Background job to evaluate pending raw posts for a specific user.
    """
    logger.info(f"Executing background task analyze_user_pending_leads_task for user ID={user_id}...")
    db = SessionLocal()
    try:
        results = analyze_pending_posts(db, user_id=user_id, limit=limit)
        return results
    except Exception as e:
        logger.error(f"analyze_user_pending_leads_task failed for user ID={user_id}: {e}", exc_info=True)
        raise e
    finally:
        db.close()
