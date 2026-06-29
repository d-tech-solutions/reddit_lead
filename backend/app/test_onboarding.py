import sys
import os
from sqlalchemy.orm import Session

# Add current folder to python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.database import SessionLocal, engine
from app.models import RedditPost, LeadAnalysis, UserPreferences
from app.onboarding_service import initialize_onboarding, process_onboarding_turn
from app.ai_service import analyze_post

def run_tests():
    try:
        # Reconfigure stdout to support printing unicode checkmarks on Windows
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass
        
    db = SessionLocal()
    print("=== STARTING PHASE 1 VERIFICATION ===")
    
    try:
        # 1. Test Onboarding Initialization
        print("\n1. Testing Onboarding Initialization...")
        first_question = initialize_onboarding(db, user_id=999) # Using dummy user 999 for test
        print(f"Initialized onboarding for user 999.")
        print(f"First Question: '{first_question}'")
        
        prefs = db.query(UserPreferences).filter(UserPreferences.user_id == 999).first()
        assert prefs is not None
        assert prefs.onboarding_status == "in_progress"
        assert len(prefs.onboarding_history) == 1
        print("Initialization checks passed successfully!")
        
        # 2. Test Onboarding Chat Turn
        print("\n2. Testing Onboarding Chat Turn...")
        user_answer = (
            "I build custom web applications and business automation tools for startups and business owners. "
            "I want to find projects involving SaaS MVPs and workflow automation. "
            "Please ignore tutorials, homework, and regular full-time job ads."
        )
        print(f"User Response: '{user_answer}'")
        
        result = process_onboarding_turn(db, user_response=user_answer, user_id=999)
        print(f"Turn response received. Status: {result.get('status')}")
        print(f"Confidence score: {result.get('confidence')}")
        
        if result.get("status") == "completed":
            print("Onboarding completed on first turn!")
            print(f"Search Intent Profile generated: {result.get('profile')}")
        else:
            print(f"Next Dynamic Question: '{result.get('question')}'")
            print("Chat turn processing passed successfully!")
            
        # 3. Test Search Intent Engine Matching
        print("\n3. Testing Search Intent Engine Lead Qualification...")
        
        # Mock Search Intent Profile to ensure predictable behavior
        test_profile = {
            "services": ["business automation", "custom web applications", "SaaS MVPs"],
            "desired_opportunities": ["startups looking for automation", "MVP builds", "business owners looking for software"],
            "target_businesses": ["startups", "small business owners"],
            "preferred_industries": [],
            "excluded_opportunities": ["job posts", "homework", "tutorials", "salary-based employment"]
        }
        
        # Scenario A: Relevant Lead
        title_relevant = "Looking for someone to build a custom SaaS MVP for restaurant automation"
        content_relevant = "Hi! I am a startup owner trying to automate my restaurant's manual ordering sheets. I want to build a custom MVP web app. Budget is around $5000."
        print(f"\nScenario A (Expecting Relevant): '{title_relevant}'")
        
        analysis_relevant = analyze_post(title_relevant, content_relevant, search_intent_profile=test_profile)
        print(f"Is Relevant: {analysis_relevant.get('relevant')}")
        print(f"Match Confidence Score: {analysis_relevant.get('score')}/100")
        print(f"Estimated Budget/Value: {analysis_relevant.get('estimated_budget')}")
        print(f"Why this lead? (Match Reasoning):")
        for reason in analysis_relevant.get("match_reasoning", []):
            print(f"  {reason}")
        print(f"Suggested reply preview: '{analysis_relevant.get('suggested_reply')[:80]}...'")
        
        # Scenario B: Irrelevant Lead (Tutorial / Homework)
        title_irrelevant = "Help with Laravel Python tutorial homework task"
        content_irrelevant = "Can anyone show me a tutorial on how to connect databases in Laravel? Doing some university homework."
        print(f"\nScenario B (Expecting Irrelevant): '{title_irrelevant}'")
        
        analysis_irrelevant = analyze_post(title_irrelevant, content_irrelevant, search_intent_profile=test_profile)
        print(f"Is Relevant: {analysis_irrelevant.get('relevant')}")
        print(f"Match Confidence Score: {analysis_irrelevant.get('score')}/100")
        print(f"Why this lead? (Match Reasoning): {analysis_irrelevant.get('match_reasoning')}")
        
        # Assertions
        assert analysis_relevant.get("relevant") is True or analysis_relevant.get("score", 0) >= 70
        assert analysis_irrelevant.get("relevant") is False or analysis_irrelevant.get("score", 0) < 50
        print("\nAll match analysis assertions passed successfully!")

    finally:
        # Cleanup test user preferences
        print("\nCleaning up test user preferences from DB...")
        db.query(UserPreferences).filter(UserPreferences.user_id == 999).delete()
        db.commit()
        db.close()
        print("Cleanup completed.")
        
    print("\n=== PHASE 1 VERIFICATION COMPLETED SUCCESSFULLY ===")

if __name__ == "__main__":
    run_tests()
