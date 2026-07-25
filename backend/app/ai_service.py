import json
import logging
import re
import httpx
from app.config import settings

logger = logging.getLogger(__name__)

def clean_json_output(text: str) -> dict:
    """Extract and parse JSON string from LLM output, handling markdown wrappers."""
    text = text.strip()
    # Check if the output is wrapped in ```json ... ``` or ``` ... ```
    match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.DOTALL)
    if match:
        text = match.group(1)
    
    try:
        return json.loads(text)
    except Exception as e:
        logger.error(f"Failed to parse LLM response as JSON. Error: {e}. Raw response: {text}")
        # Return a safe fallback structure
        return {
            "relevant": False,
            "score": 0,
            "industry": "General",
            "urgency": "Low",
            "intent": "Unknown",
            "estimated_budget": "Unspecified",
            "recommended_service": "General Development",
            "summary": "Failed to analyze post content.",
            "suggested_reply": "Hi! I noticed your post and would love to discuss how I can help with your project.",
            "match_reasoning": []
        }

def analyze_post(title: str, content: str, search_intent_profile: dict = None) -> dict:
    """Call OpenAI completions API to analyze a Reddit post against the user's Search Intent Profile."""
    
    # Default search intent profile if none is provided
    if not search_intent_profile:
        search_intent_profile = {
            "services": ["Web Development", "Mobile App Development", "SaaS MVPs", "AI Consulting", "Workflow Automation"],
            "desired_opportunities": ["startups needing developers", "business owners looking for software development", "automation projects"],
            "target_businesses": ["startups", "small business owners"],
            "preferred_industries": [],
            "excluded_opportunities": ["job posts", "homework", "tutorials", "full-time employment"]
        }

    if not settings.OPENAI_API_KEY or settings.OPENAI_API_KEY == "your_openai_api_key_here":
        logger.warning("OpenAI API key is not configured. Returning mock analysis.")
        return {
            "relevant": True,
            "score": 85,
            "industry": "Software",
            "urgency": "Medium",
            "intent": "SaaS MVP Development",
            "estimated_budget": "$5k-$10k",
            "recommended_service": "Web Development",
            "summary": "Mock summary: User is looking to build a custom application (API Key missing).",
            "suggested_reply": "Hi! I saw your post. I build custom web applications and SaaS MVPs. Let me know if you would like to discuss this further.",
            "match_reasoning": [
                "Matches your preferred opportunity: SaaS MVP Development (Mock Mode)",
                "Startup founder detected (Mock Mode)"
            ]
        }

    url = "https://api.openai.com/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {settings.OPENAI_API_KEY}",
        "Content-Type": "application/json"
    }

    system_prompt = (
        "You are the Search Intent Engine and Lead Intelligence Engine for LeadRadar AI, an AI-powered Lead Intelligence Platform.\n"
        "Your task is to evaluate a Reddit post against a user's Search Intent Profile and decide if it is a relevant opportunity.\n\n"
        "=== USER SEARCH INTENT PROFILE ===\n"
        f"{json.dumps(search_intent_profile, indent=2)}\n\n"
        "=== GUIDELINES ===\n"
        "1. Determine if the post matches the user's services and desired opportunities.\n"
        "2. Make sure the post does NOT contain any elements matching the user's excluded opportunities (e.g. homework, tutorials, standard job ads).\n"
        "3. Look for buying intent, authority signals (e.g., founder, owner), and solveable business problems.\n"
        "4. Calculate a match confidence score (0-100).\n"
        "You are an expert sales lead analyzer for freelance developers, AI consultants, and digital agencies.\n"
        "Your task is to analyze a Reddit post and output a JSON object to qualify it as a potential business lead for the user.\n\n"
        "Evaluate the post and output EXACTLY this JSON structure:\n"
        "{\n"
        '  "relevant": <boolean indicating if this is a qualified match for the user\'s preferences>,\n'
        '  "score": <0-100 integer representing match quality and buying intent. 70+ indicates a strong lead>,\n'
        '  "industry": "<e.g., E-commerce, Restaurant, Finance, Healthcare, Real Estate, or General if unknown>",\n'
        '  "urgency": "<Low, Medium, or High>",\n'
        '  "intent": "<brief description of what they need, e.g., CRM setup, landing page, custom SaaS, etc.>",\n'
        '  "estimated_budget": "<brief mention of budget, e.g., \'$5000\', \'Unspecified\', \'Under $1000\'>",\n'
        '  "recommended_service": "<the service we should offer matching the user\'s capabilities, e.g., Web Development, AI Integration, Flutter App>",\n'
        '  "summary": "<1-2 sentence summary of the project and user requirements>",\n'
        '  "match_reasoning": [<list of strings detailing exactly why this post fits or does not fit user preferences>],\n'
        '  "suggested_reply": "<a highly customized, friendly, professional pitch reply addressing their specific problem and showcasing value. Keep it natural, conversational, and avoid sounding like generic ChatGPT boilerplate. Make it ready to send on Reddit. Do not mention that you are an AI or bot.>"\n'
        "}\n\n"
        "Output ONLY the raw JSON object. Do not wrap it in markdown block characters."
    )

    user_content = f"Title: {title}\n\nContent: {content or '[No Content]'}"

    payload = {
        "model": settings.OPENAI_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content}
        ],
        "temperature": 0.2,
        "response_format": {"type": "json_object"}
    }

    try:
        logger.info(f"Sending request to OpenAI using model: {settings.OPENAI_MODEL}")
        response = httpx.post(url, headers=headers, json=payload, timeout=20.0)
        response.raise_for_status()
        
        result_data = response.json()
        choices = result_data.get("choices", [])
        if not choices:
            raise Exception("No completion choices returned from OpenAI.")
            
        content_out = choices[0].get("message", {}).get("content", "")
        return clean_json_output(content_out)
    except Exception as e:
        logger.error(f"OpenAI API request failed: {e}", exc_info=True)
        raise e


def generate_embedding(text: str) -> list:
    """Generate a vector embedding for the given text using OpenAI's API."""
    if not settings.OPENAI_API_KEY or settings.OPENAI_API_KEY == "your_openai_api_key_here":
        logger.warning("OpenAI API key is not configured. Returning mock embedding.")
        # Return a mock 1536-dimension float array
        return [0.01] * 1536

    url = "https://api.openai.com/v1/embeddings"
    headers = {
        "Authorization": f"Bearer {settings.OPENAI_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "input": text,
        "model": "text-embedding-3-small"
    }

    try:
        logger.info("Sending embedding generation request to OpenAI...")
        response = httpx.post(url, headers=headers, json=payload, timeout=15.0)
        response.raise_for_status()
        
        result_data = response.json()
        data = result_data.get("data", [])
        if not data:
            raise Exception("No embedding data returned from OpenAI.")
            
        return data[0].get("embedding", [])
    except Exception as e:
        logger.error(f"OpenAI embedding generation failed: {e}", exc_info=True)
        # Fallback to mock vector rather than crashing
        return [0.0] * 1536


def extract_post_intelligence(title: str, content: str) -> dict:
    """Call OpenAI completions API to analyze a Reddit post and extract lead intelligence fields."""
    if not settings.OPENAI_API_KEY or settings.OPENAI_API_KEY == "your_openai_api_key_here":
        logger.warning("OpenAI API key is not configured. Returning mock intelligence extraction.")
        return {
            "problem": "Mock: Client needs custom automation pipelines.",
            "industry": "Software",
            "services_needed": ["Workflow Automation", "Web Development"],
            "buying_intent": "High",
            "urgency": "Medium",
            "estimated_budget": "$5k-$10k",
            "summary": "Mock summary: Founder wants to automate their CRM data flow."
        }

    url = "https://api.openai.com/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {settings.OPENAI_API_KEY}",
        "Content-Type": "application/json"
    }

    system_prompt = (
        "You are the Lead Intelligence Extractor for LeadRadar AI.\n"
        "Your task is to analyze a raw Reddit post and extract structured business lead intelligence.\n\n"
        "=== GUIDELINES ===\n"
        "1. Extract the core business problem being discussed.\n"
        "2. Identify the target industry (e.g. E-commerce, Restaurant, Real Estate, Healthcare, Software, or General if unknown).\n"
        "3. List specific services needed (e.g. ['Web Development', 'Mobile App Development', 'AI Integration', 'Workflow Automation']).\n"
        "4. Determine the buying intent strength: 'Low', 'Medium', or 'High' based on concrete indicators (explicit calls for hire, describing a project, authority role).\n"
        "5. Determine the urgency: 'Low', 'Medium', or 'High' based on timeline mentions.\n"
        "6. Extract the estimated project budget. If not mentioned or implied, write 'Unspecified'.\n"
        "7. Provide a concise 1-2 sentence business-focused summary of the post.\n\n"
        "Evaluate the post and output EXACTLY this JSON structure:\n"
        "{\n"
        '  "problem": "<detailed description of the business problem they are trying to solve>",\n'
        '  "industry": "<identified industry or General>",\n'
        '  "services_needed": ["<service 1>", "<service 2>", ...],\n'
        '  "buying_intent": "<Low, Medium, or High>",\n'
        '  "urgency": "<Low, Medium, or High>",\n'
        '  "estimated_budget": "<e.g., $5000, Unspecified, Under $1000>",\n'
        '  "summary": "<1-2 sentence summary of the project and user requirements>"\n'
        "}\n\n"
        "Output ONLY the raw JSON object. Do not wrap it in markdown block characters."
    )

    user_content = f"Title: {title}\n\nContent: {content or '[No Content]'}"

    payload = {
        "model": settings.OPENAI_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content}
        ],
        "temperature": 0.1,
        "response_format": {"type": "json_object"}
    }

    try:
        logger.info(f"Sending extraction request to OpenAI using model: {settings.OPENAI_MODEL}")
        response = httpx.post(url, headers=headers, json=payload, timeout=20.0)
        response.raise_for_status()
        
        result_data = response.json()
        choices = result_data.get("choices", [])
        if not choices:
            raise Exception("No completion choices returned from OpenAI.")
            
        content_out = choices[0].get("message", {}).get("content", "")
        return clean_json_output(content_out)
    except Exception as e:
        logger.error(f"OpenAI intelligence extraction failed: {e}", exc_info=True)
        # Return fallback structure
        return {
            "problem": "Failed to analyze post content.",
            "industry": "General",
            "services_needed": [],
            "buying_intent": "Low",
            "urgency": "Low",
            "estimated_budget": "Unspecified",
            "summary": "Failed to analyze post content."
        }


def personal_match_lead(profile: dict, intelligence: dict, title: str) -> dict:
    """
    Call OpenAI API to evaluate a post's pre-extracted intelligence against a user's Search Intent Profile.
    Returns relevance (bool), score (0-100), recommended service, match reasons, and suggested pitch reply.
    """
    if not settings.OPENAI_API_KEY or settings.OPENAI_API_KEY == "your_openai_api_key_here":
        logger.warning("OpenAI API key is not configured. Returning mock personal match.")
        return {
            "relevant": True,
            "score": 85,
            "recommended_service": intelligence.get("services_needed", ["Web Development"])[0] if intelligence.get("services_needed") else "Web Development",
            "match_reasoning": [
                f"Matches services: {', '.join(profile.get('services', []))}",
                "Identified business problem aligns with your capabilities"
            ],
            "suggested_reply": f"Hi! I noticed your post about: {intelligence.get('summary', 'your project')}. I specialize in the services you need and would love to help you build this."
        }

    url = "https://api.openai.com/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {settings.OPENAI_API_KEY}",
        "Content-Type": "application/json"
    }

    system_prompt = (
        "You are the AI Personal Matcher for LeadRadar AI.\n"
        "Your task is to evaluate a Reddit post's pre-extracted intelligence against a user's Search Intent Profile.\n"
        "Determine if this post represents a highly relevant opportunity for the user, calculate a match score (0-100), and write a customized outreach pitch.\n\n"
        "=== USER SEARCH INTENT PROFILE ===\n"
        f"{json.dumps(profile, indent=2)}\n\n"
        "=== POST EXTRACTED INTELLIGENCE ===\n"
        f"{json.dumps(intelligence, indent=2)}\n\n"
        "=== GUIDELINES ===\n"
        "1. Confirm if the post is relevant to the user's services, target businesses, and desired opportunities.\n"
        "2. Ensure the post does NOT match any items in the user's excluded_opportunities.\n"
        "3. Compute a match score (0-100) reflecting how well the opportunity fits the user's services and intent.\n"
        "4. Choose the specific recommended service from the user's services that solves the poster's problem.\n"
        "5. Compile 2-4 specific match reasoning bullet points explaining why this post is a fit.\n"
        "6. Draft a highly personalized, warm, professional outreach pitch reply that addresses their problem directly and introduces the user's service. "
        "Keep it natural, conversational, and ready to send on Reddit. Do not mention you are an AI or bot.\n\n"
        "Evaluate the details and output EXACTLY this JSON structure:\n"
        "{\n"
        '  "relevant": <boolean indicating if this is a qualified match for this specific user\'s preferences>,\n'
        '  "score": <0-100 integer representing match quality for the user>,\n'
        '  "recommended_service": "<the service from the user\'s profile to recommend, e.g., Web Development>",\n'
        '  "match_reasoning": [<list of strings detailing why this post matches user preferences>],\n'
        '  "suggested_reply": "<customized pitch reply to send on Reddit>"\n'
        "}\n\n"
        "Output ONLY the raw JSON object. Do not wrap it in markdown block characters."
    )

    user_content = f"Post Title: {title}\nSummary: {intelligence.get('summary', '')}"

    payload = {
        "model": settings.OPENAI_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content}
        ],
        "temperature": 0.2,
        "response_format": {"type": "json_object"}
    }

    try:
        logger.info(f"Sending personal match request to OpenAI using model: {settings.OPENAI_MODEL}")
        response = httpx.post(url, headers=headers, json=payload, timeout=20.0)
        response.raise_for_status()
        
        result_data = response.json()
        choices = result_data.get("choices", [])
        if not choices:
            raise Exception("No completion choices returned from OpenAI.")
            
        content_out = choices[0].get("message", {}).get("content", "")
        return clean_json_output(content_out)
    except Exception as e:
        logger.error(f"OpenAI personal match failed: {e}", exc_info=True)
        return {
            "relevant": False,
            "score": 0,
            "recommended_service": "General",
            "match_reasoning": ["Failed to analyze match qualification."],
            "suggested_reply": "Hi! I saw your post. Let me know if you would like to discuss this further."
        }
