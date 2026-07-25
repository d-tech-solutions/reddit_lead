import json
import logging
import httpx
from sqlalchemy.orm import Session
from app.config import settings
from app import crud

logger = logging.getLogger(__name__)

def initialize_onboarding(db: Session, user_id: int = 1) -> str:
    """Initialize or reset the conversational onboarding flow for a user."""
    # Find or create UserPreferences
    prefs = crud.get_user_preferences(db, user_id=user_id)
    
    first_question = "What kinds of opportunities would you like me to notify you about?"
    
    initial_history = [
        {"role": "assistant", "content": first_question}
    ]
    
    if not prefs:
        prefs = crud.create_user_preferences(db, user_id=user_id)
    
    prefs.onboarding_status = "in_progress"
    prefs.onboarding_history = initial_history
    prefs.question_count = 1
    prefs.confidence = 0.0
    prefs.profile_json = None
    prefs.embedding = None
        
    try:
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to initialize onboarding in DB: {e}")
        raise e
        
    return first_question

def process_onboarding_turn(db: Session, user_response: str, user_id: int = 1) -> dict:
    """Process a single response from the user and determine the next action."""
    prefs = crud.get_user_preferences(db, user_id=user_id)
    if not prefs:
        # Auto-initialize if not exists
        initialize_onboarding(db, user_id=user_id)
        prefs = crud.get_user_preferences(db, user_id=user_id)

    # Append user response to history
    history = list(prefs.onboarding_history or [])
    history.append({"role": "user", "content": user_response})
    
    # Check if OpenAI API Key is missing and return mock response if so
    if not settings.OPENAI_API_KEY or settings.OPENAI_API_KEY == "your_openai_api_key_here":
        logger.warning("OpenAI API key missing. Mocking onboarding conversation turn.")
        
        # Check stopping conditions (mock mode)
        if prefs.question_count >= 6:
            mock_profile = {
                "services": ["SaaS MVPs", "Workflow Automation"],
                "desired_opportunities": ["startups looking for developers"],
                "target_businesses": ["startups"],
                "preferred_industries": ["Software"],
                "excluded_opportunities": ["job posts"]
            }
            # Generate embedding for Search Intent Profile
            services_str = ", ".join(mock_profile["services"])
            desires_str = ", ".join(mock_profile["desired_opportunities"])
            targets_str = ", ".join(mock_profile["target_businesses"])
            industries_str = ", ".join(mock_profile["preferred_industries"])
            profile_text = f"Services offered: {services_str}. Desired opportunities: {desires_str}. Target customers: {targets_str}. Preferred industries: {industries_str}."
            
            try:
                from app.ai_service import generate_embedding
                prefs.embedding = generate_embedding(profile_text)
                logger.info(f"Generated profile embedding (Mock Mode) for user ID={user_id}")
            except Exception as embed_err:
                logger.error(f"Failed to generate profile embedding (Mock Mode): {embed_err}")
                
            prefs.onboarding_status = "completed"
            prefs.profile_json = mock_profile
            prefs.confidence = 0.95
            prefs.onboarding_history = history
            db.commit()
            return {
                "status": "completed",
                "profile": mock_profile,
                "confidence": 0.95,
                "message": "Preferences setup completed successfully! Your search intent profile is active (Mock Mode)."
            }
            
        mock_question = "What type of clients do you usually enjoy working with?"
        history.append({"role": "assistant", "content": mock_question})
        prefs.onboarding_history = history
        prefs.question_count += 1
        prefs.confidence = 0.5
        db.commit()
        return {
            "status": "in_progress",
            "question": mock_question,
            "question_count": prefs.question_count,
            "confidence": 0.5
        }

    # Call OpenAI API to evaluate the conversation
    url = "https://api.openai.com/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {settings.OPENAI_API_KEY}",
        "Content-Type": "application/json"
    }

    system_prompt = (
        "You are the AI Conversation Engine for LeadRadar AI, an AI-powered Lead Intelligence Platform.\n"
        "Your task is to analyze the user preferences setup chat history and build/refine an internal Search Intent Profile.\n"
        "We do NOT want to use a predefined list of questions. Instead, dynamically identify the most critical missing context, and ask exactly one follow-up question.\n\n"
        "The Search Intent Profile contains:\n"
        "- services: List of services they offer (e.g., custom web apps, business automation, SaaS MVPs).\n"
        "- desired_opportunities: Specific target client requests/needs they are looking for.\n"
        "- target_businesses: Ideal buyer/persona types (e.g., startups, local restaurant owners).\n"
        "- preferred_industries: Industries they prefer.\n"
        "- excluded_opportunities: Post types, job offers, or keywords to ignore (e.g., homework, tutorials, full-time jobs).\n"
        "- buying_intent_preferences: Boolean preferences like require_budget_mention and allow_implied_needs.\n\n"
        "Evaluate the chat history and:\n"
        "1. Populate or refine the fields of the Search Intent Profile.\n"
        "2. Compute a confidence score (from 0.0 to 1.0) indicating how complete the profile is.\n"
        "3. If the confidence is < 0.90, generate exactly ONE follow-up question to retrieve the most important missing information.\n"
        "4. If the confidence is >= 0.90, do not ask a follow-up question.\n\n"
        "You must respond with EXACTLY this JSON structure:\n"
        "{\n"
        '  "confidence": <float between 0.0 and 1.0>,\n'
        '  "profile": {\n'
        '    "services": [...],\n'
        '    "desired_opportunities": [...],\n'
        '    "target_businesses": [...],\n'
        '    "preferred_industries": [...],\n'
        '    "excluded_opportunities": [...],\n'
        '    "buying_intent_preferences": {\n'
        '      "require_budget_mention": <boolean>,\n'
        '      "allow_implied_needs": <boolean>\n'
        '    }\n'
        '  },\n'
        '  "missing_info_description": "<description of missing context>",\n'
        '  "next_question": "<exactly one follow-up question, or empty if confidence >= 0.90>"\n'
        "}\n\n"
        "Output ONLY the raw JSON object. Do not wrap in markdown block characters."
    )

    # Format history messages for the API (mapping assistant/user roles)
    api_messages = [{"role": "system", "content": system_prompt}]
    for msg in history:
        api_messages.append({"role": msg["role"], "content": msg["content"]})

    payload = {
        "model": settings.OPENAI_MODEL,
        "messages": api_messages,
        "temperature": 0.2,
        "response_format": {"type": "json_object"}
    }

    try:
        response = httpx.post(url, headers=headers, json=payload, timeout=20.0)
        response.raise_for_status()
        result_data = response.json()
        
        choices = result_data.get("choices", [])
        if not choices:
            raise Exception("No completion choices returned from OpenAI.")
            
        content_out = choices[0].get("message", {}).get("content", "")
        analysis = json.loads(content_out.strip())
        
        confidence = float(analysis.get("confidence", 0.0))
        profile = analysis.get("profile", {})
        next_question = analysis.get("next_question", "")
        
        # Check stopping conditions
        max_questions_reached = prefs.question_count >= 6
        confidence_met = confidence >= 0.90
        
        if confidence_met or max_questions_reached or not next_question:
            # Generate embedding for Search Intent Profile
            services_str = ", ".join(profile.get("services", []))
            desires_str = ", ".join(profile.get("desired_opportunities", []))
            targets_str = ", ".join(profile.get("target_businesses", []))
            industries_str = ", ".join(profile.get("preferred_industries", []))
            
            profile_text = (
                f"Services offered: {services_str}. "
                f"Desired opportunities: {desires_str}. "
                f"Target customers: {targets_str}. "
                f"Preferred industries: {industries_str}."
            )
            
            try:
                from app.ai_service import generate_embedding
                prefs.embedding = generate_embedding(profile_text)
                logger.info(f"Generated profile embedding for user ID={user_id}")
            except Exception as embed_err:
                logger.error(f"Failed to generate profile embedding: {embed_err}")

            # Complete onboarding
            prefs.onboarding_status = "completed"
            prefs.profile_json = profile
            prefs.confidence = confidence
            prefs.onboarding_history = history
            db.commit()
            return {
                "status": "completed",
                "profile": profile,
                "confidence": confidence,
                "message": "Preferences setup completed successfully! Your search intent profile is active."
            }
        else:
            # Continue onboarding
            history.append({"role": "assistant", "content": next_question})
            prefs.onboarding_history = history
            prefs.question_count += 1
            prefs.confidence = confidence
            db.commit()
            return {
                "status": "in_progress",
                "question": next_question,
                "question_count": prefs.question_count,
                "confidence": confidence
            }
            
    except Exception as e:
        logger.error(f"OpenAI onboarding turn processing failed: {e}", exc_info=True)
        # Fallback to manual question / complete to avoid crash
        fallback_question = "Could you specify any types of posts or topics you would like me to filter out/ignore?"
        history.append({"role": "assistant", "content": fallback_question})
        prefs.onboarding_history = history
        prefs.question_count += 1
        db.commit()
        return {
            "status": "in_progress",
            "question": fallback_question,
            "question_count": prefs.question_count,
            "confidence": prefs.confidence
        }
