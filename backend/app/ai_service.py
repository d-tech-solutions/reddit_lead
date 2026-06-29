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
