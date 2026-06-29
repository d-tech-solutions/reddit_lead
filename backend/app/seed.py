import sys
import os

# Add parent directory to path to enable importing app
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.database import SessionLocal, engine, Base
from app.models import User, UserPreferences
from app.auth_service import get_password_hash

def seed_db():
    print("Dropping existing tables...")
    Base.metadata.drop_all(bind=engine)
    print("Initializing database tables...")
    Base.metadata.create_all(bind=engine)
    
    db = SessionLocal()
    try:
        # Check if the superadmin user already exists
        admin_email = "admin@leadradar.com"
        print(f"Checking if superadmin user '{admin_email}' exists...")
        admin = db.query(User).filter(User.email == admin_email).first()
        
        if not admin:
            print("Creating superadmin user...")
            hashed_pw = get_password_hash("1111111111")
            admin = User(
                email=admin_email,
                hashed_password=hashed_pw,
                full_name="Super Admin",
                is_admin=True
            )
            db.add(admin)
            db.flush() # Flush to get the admin.id
            
            # Initialize preferences for the admin
            print("Initializing preferences for superadmin...")
            prefs = UserPreferences(
                user_id=admin.id,
                onboarding_status="not_started",
                onboarding_history=[],
                question_count=0,
                confidence=0.0,
                profile_json=None
            )
            db.add(prefs)
            
            db.commit()
            print("Superadmin user and preferences seeded successfully!")
        else:
            print("Superadmin user already exists. Skipping.")
            
    except Exception as e:
        db.rollback()
        print(f"Error seeding database: {e}")
        sys.exit(1)
    finally:
        db.close()

if __name__ == "__main__":
    seed_db()
