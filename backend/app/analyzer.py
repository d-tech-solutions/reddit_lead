import logging
import time
import math
from sqlalchemy.orm import Session
from app.config import settings
from app import crud
from app.models import RedditPost, RedditPostIntelligence, UserPreferences
from app.ai_service import (
    generate_embedding,
    extract_post_intelligence,
    personal_match_lead
)
from app.notifier import send_lead_notification

logger = logging.getLogger(__name__)


def python_cosine_similarity(v1, v2) -> float:
    """Calculate the cosine similarity between two lists of floats in Python."""
    if not v1 or not v2 or len(v1) != len(v2):
        return 0.0
    dot_product = sum(x * y for x, y in zip(v1, v2))
    mag1 = math.sqrt(sum(x * x for x in v1))
    mag2 = math.sqrt(sum(y * y for y in v2))
    if mag1 == 0 or mag2 == 0:
        return 0.0
    return dot_product / (mag1 * mag2)


def process_single_post_intelligence(db: Session, post_id: int) -> RedditPostIntelligence:
    """
    Ensure the post has undergone AI Content Understanding once.
    Extracts structured fields and generates a 1536-dimension content embedding.
    """
    # 1. Check if intelligence already exists
    intel = crud.get_post_intelligence(db, post_id=post_id)
    if intel:
        return intel

    # 2. Fetch post
    post = crud.get_post_by_id(db, post_id=post_id)
    if not post:
        raise ValueError(f"Post with ID {post_id} not found.")

    logger.info(f"Running AI Content Understanding (once-per-post) for post ID={post.id}...")
    
    # 3. Extract structured features via LLM
    extracted_intel = extract_post_intelligence(post.title, post.content)
    
    # 4. Generate content embedding using Title + Summary
    semantic_text = f"Title: {post.title}. Summary: {extracted_intel.get('summary', '')}."
    embedding = generate_embedding(semantic_text)
    
    # 5. Create intelligence record
    intel_data = {
        "post_id": post.id,
        "problem": extracted_intel.get("problem"),
        "industry": extracted_intel.get("industry", "General"),
        "services_needed": extracted_intel.get("services_needed", []),
        "buying_intent": extracted_intel.get("buying_intent", "Low"),
        "urgency": extracted_intel.get("urgency", "Low"),
        "estimated_budget": extracted_intel.get("estimated_budget", "Unspecified"),
        "summary": extracted_intel.get("summary", ""),
        "embedding": embedding
    }
    
    intel = crud.create_post_intelligence(db, intel_data)
    db.commit()
    
    return intel


def match_post_to_users_pipeline(db: Session, post_id: int, top_n: int = 10) -> dict:
    """
    Evolves matching pipeline to match a single post against candidate users.
    Used for background job workers.
    """
    post = crud.get_post_by_id(db, post_id=post_id)
    if not post:
        return {"matched_users": 0}

    # Ensure post intelligence is generated
    intel = process_single_post_intelligence(db, post_id)
    if not intel or not intel.embedding:
        return {"matched_users": 0}

    # Query all users with completed preferences and embeddings
    # Check dialect for cosine similarity sorting
    dialect_name = db.bind.dialect.name
    
    if dialect_name == 'postgresql':
        # Native pgvector cosine distance: <=> operator
        distance = UserPreferences.embedding.cosine_distance(intel.embedding)
        candidates = db.query(UserPreferences, distance.label('distance'))\
                       .filter(UserPreferences.onboarding_status == 'completed')\
                       .filter(UserPreferences.embedding != None)\
                       .order_by(distance)\
                       .limit(top_n)\
                       .all()
    else:
        # SQLite / other dialect fallback in Python
        prefs_list = db.query(UserPreferences)\
                       .filter(UserPreferences.onboarding_status == 'completed')\
                       .filter(UserPreferences.embedding != None)\
                       .all()
        candidates_with_dist = []
        for p in prefs_list:
            dist = 1.0 - python_cosine_similarity(p.embedding, intel.embedding)
            candidates_with_dist.append((p, dist))
        candidates_with_dist.sort(key=lambda x: x[1])
        candidates = candidates_with_dist[:top_n]

    logger.info(f"Post ID={post_id} vector matching found {len(candidates)} candidate users.")
    
    matched_count = 0
    for item in candidates:
        # Handle tuple output from PostgreSQL query vs simple list output from SQLite fallback
        if isinstance(item, tuple):
            prefs, dist = item[0], item[1]
        else:
            prefs, dist = item[0], item[1]
            
        user_id = prefs.user_id
        
        # Check similarity threshold (similarity >= 0.65)
        similarity = 1.0 - dist
        if similarity < 0.65:
            continue
            
        # Check if already analyzed
        exists = crud.get_lead_analysis(db, post_id=post_id, user_id=user_id)
        if exists:
            continue
            
        # Run personal matcher (LLM check)
        logger.info(f"Running AI Personal Matcher for post ID={post_id} and user ID={user_id} (distance={dist:.4f})...")
        match_res = personal_match_lead(prefs.profile_json, {
            "problem": intel.problem,
            "industry": intel.industry,
            "services_needed": intel.services_needed,
            "buying_intent": intel.buying_intent,
            "urgency": intel.urgency,
            "estimated_budget": intel.estimated_budget,
            "summary": intel.summary
        }, post.title)
        
        # Save LeadAnalysis junction row
        db_analysis = crud.create_lead_analysis(db, {
            "post_id": post_id,
            "user_id": user_id,
            "relevant": match_res.get("relevant", False),
            "score": match_res.get("score", 0),
            "industry": intel.industry,
            "urgency": intel.urgency,
            "intent": intel.problem[:200] if intel.problem else "Unknown",
            "estimated_budget": intel.estimated_budget,
            "recommended_service": match_res.get("recommended_service", "General Development"),
            "summary": intel.summary,
            "suggested_reply": match_res.get("suggested_reply", ""),
            "match_reasoning": match_res.get("match_reasoning", [])
        })
        db.commit()
        if db_analysis.relevant:
            matched_count += 1
        
        # Dispatch Telegram notification if relevant and above threshold
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
                logger.error(f"Failed to dispatch Telegram notification for post ID={post_id}: {notify_err}", exc_info=True)
                
    return {"matched_users": matched_count}


def analyze_pending_posts(db: Session, user_id: int, limit: int = 10) -> dict:
    """
    Orchestrates pending raw posts processing, qualifying them via vector search first.
    Called by HTTP trigger endpoints.
    """
    # Retrieve user intent preferences profile
    prefs = crud.get_user_preferences(db, user_id=user_id)
    if not prefs or prefs.onboarding_status != "completed" or not prefs.profile_json or not prefs.embedding:
        logger.warning(f"User ID={user_id} has not completed onboarding. Skipping analysis.")
        return {"processed": 0, "successful": 0}

    # Find posts that do not have an associated LeadAnalysis entry for this specific user
    pending_posts = crud.get_pending_posts_for_user(db, user_id=user_id, limit=limit)
    total_found = len(pending_posts)
    if total_found == 0:
        logger.info(f"No pending Reddit posts found for AI analysis for user ID={user_id}.")
        return {"processed": 0, "successful": 0}

    logger.info(f"Found {total_found} pending posts to analyze for user ID={user_id} (limit={limit}).")

    successful_count = 0
    for post in pending_posts:
        try:
            # 1. Ensure post has intelligence details extracted
            intel = process_single_post_intelligence(db, post.id)
            if not intel or not intel.embedding:
                continue

            # 2. Check semantic similarity distance
            similarity = python_cosine_similarity(prefs.embedding, intel.embedding)
            # A similarity score >= 0.65 represents a reasonable match potential
            is_semantic_candidate = similarity >= 0.65

            if not is_semantic_candidate:
                # Store non-matching qualification to avoid evaluating again
                crud.create_lead_analysis(db, {
                    "post_id": post.id,
                    "user_id": user_id,
                    "relevant": False,
                    "score": 0,
                    "industry": intel.industry,
                    "urgency": intel.urgency,
                    "intent": intel.problem[:200] if intel.problem else "Unknown",
                    "estimated_budget": intel.estimated_budget,
                    "recommended_service": "General",
                    "summary": intel.summary,
                    "suggested_reply": "",
                    "match_reasoning": ["Vector similarity score was too low."]
                })
                db.commit()
                successful_count += 1
                continue

            # 3. If candidate matches vector check, run Personal Matcher (LLM qualification)
            logger.info(f"Post ID={post.id} title='{post.title[:30]}...' passed vector filter (similarity={similarity:.4f}). Calling Personal Matcher...")
            match_res = personal_match_lead(prefs.profile_json, {
                "problem": intel.problem,
                "industry": intel.industry,
                "services_needed": intel.services_needed,
                "buying_intent": intel.buying_intent,
                "urgency": intel.urgency,
                "estimated_budget": intel.estimated_budget,
                "summary": intel.summary
            }, post.title)

            # 4. Persist the qualified analysis
            db_analysis = crud.create_lead_analysis(db, {
                "post_id": post.id,
                "user_id": user_id,
                "relevant": match_res.get("relevant", False),
                "score": match_res.get("score", 0),
                "industry": intel.industry,
                "urgency": intel.urgency,
                "intent": intel.problem[:200] if intel.problem else "Unknown",
                "estimated_budget": intel.estimated_budget,
                "recommended_service": match_res.get("recommended_service", "General Development"),
                "summary": intel.summary,
                "suggested_reply": match_res.get("suggested_reply", ""),
                "match_reasoning": match_res.get("match_reasoning", [])
            })
            db.commit()
            successful_count += 1

            # 5. Dispatch Telegram notification if relevant and above threshold
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
            time.sleep(0.5)

        except Exception as e:
            db.rollback()
            logger.error(f"Error during matching pipeline for post ID={post.id} and user ID={user_id}: {e}", exc_info=True)

    return {
        "processed": total_found,
        "successful": successful_count
    }
