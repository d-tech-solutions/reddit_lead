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
            "score": 0,
            "industry": "General",
            "urgency": "Low",
            "intent": "Unknown",
            "estimated_budget": "Unspecified",
            "recommended_service": "General Development",
            "summary": "Failed to analyze post content.",
            "suggested_reply": "Hi! I noticed your post and would love to discuss how I can help with your project."
        }

def analyze_post(title: str, content: str) -> dict:
    """Call OpenRouter completions API to analyze a Reddit post's lead quality."""
    if not settings.OPENROUTER_API_KEY or settings.OPENROUTER_API_KEY == "your_openrouter_api_key_here":
        logger.warning("OpenRouter API key is not configured. Returning mock analysis.")
        return {
            "score": 50,
            "industry": "Software",
            "urgency": "Medium",
            "intent": "General inquiry",
            "estimated_budget": "Unspecified",
            "recommended_service": "Consulting",
            "summary": "Mock summary (API Key missing).",
            "suggested_reply": "Hi! I saw your post. Feel free to reach out to discuss details."
        }

    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {settings.OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/dharanidharan/reddit-lead",
        "X-Title": "LeadRadar AI"
    }

    system_prompt = (
        "You are an expert sales lead analyzer for freelance developers, AI consultants, and digital agencies.\n"
        "Your task is to analyze a Reddit post and output a JSON object to qualify it as a potential business lead.\n\n"
        "Target client services include:\n"
        "- Web Development (e.g. React, Next.js, Laravel, custom websites)\n"
        "- Mobile App Development (e.g. Flutter, iOS, Android)\n"
        "- SaaS MVP development\n"
        "- AI Consulting & Custom AI Integrations\n"
        "- Workflow Automation\n\n"
        "Evaluate the post and output EXACTLY this JSON structure:\n"
        "{\n"
        '  "score": <0-100 integer representing lead quality/buying intent. 70+ indicates a strong lead needing a developer/agency>,\n'
        '  "industry": "<e.g., E-commerce, Restaurant, Finance, Healthcare, Real Estate, or General if unknown>",\n'
        '  "urgency": "<Low, Medium, or High>",\n'
        '  "intent": "<brief description of what they need, e.g., CRM setup, landing page, custom SaaS, etc.>",\n'
        '  "estimated_budget": "<brief mention of budget, e.g., \'$5000\', \'Unspecified\', \'Under $1000\'>",\n'
        '  "recommended_service": "<the service we should offer, e.g., Web Development, AI Integration, Flutter App>",\n'
        '  "summary": "<1-2 sentence summary of the project and user requirements>",\n'
        '  "suggested_reply": "<a highly customized, friendly, professional pitch reply addressing their specific problem and showcasing value. Keep it natural, conversational, and avoid sounding like generic ChatGPT boilerplate. Make it ready to send on Reddit. Do not mention that you are an AI or bot.>"\n'
        "}\n\n"
        "Output ONLY the raw JSON object. Do not wrap it in markdown block characters."
    )

    user_content = f"Title: {title}\n\nContent: {content or '[No Content]'}"

    payload = {
        "model": settings.OPENROUTER_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content}
        ],
        "temperature": 0.2
    }

    try:
        logger.info(f"Sending request to OpenRouter using model: {settings.OPENROUTER_MODEL}")
        response = httpx.post(url, headers=headers, json=payload, timeout=20.0)
        response.raise_for_status()
        
        result_data = response.json()
        choices = result_data.get("choices", [])
        if not choices:
            logger.error("No completion choices returned from OpenRouter.")
            return clean_json_output("")
            
        content_out = choices[0].get("message", {}).get("content", "")
        return clean_json_output(content_out)
    except Exception as e:
        logger.error(f"OpenRouter API request failed: {e}", exc_info=True)
        return clean_json_output("")
