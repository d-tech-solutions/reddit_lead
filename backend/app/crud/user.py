from sqlalchemy.orm import Session
from typing import List, Optional
from app.models import User, UserPreferences

def get_user_by_email(db: Session, email: str) -> Optional[User]:
    """
    Retrieve a User record from the database based on their email address.
    
    Args:
        db (Session): Active SQLAlchemy database session.
        email (str): Email address of the user to look up.
        
    Returns:
        Optional[User]: The User model instance if found, otherwise None.
    """
    return db.query(User).filter(User.email == email).first()

def get_user_by_id(db: Session, user_id: int) -> Optional[User]:
    """
    Retrieve a User record from the database based on their unique integer ID.
    
    Args:
        db (Session): Active SQLAlchemy database session.
        user_id (int): Unique primary key ID of the user.
        
    Returns:
        Optional[User]: The User model instance if found, otherwise None.
    """
    return db.query(User).filter(User.id == user_id).first()

def get_all_users(db: Session) -> List[User]:
    """
    Retrieve all User records stored in the database. Primarily used by administrators.
    
    Args:
        db (Session): Active SQLAlchemy database session.
        
    Returns:
        List[User]: A list containing all User database instances.
    """
    return db.query(User).all()

def create_user(db: Session, email: str, hashed_password: str, full_name: Optional[str] = None, is_admin: bool = False) -> User:
    """
    Create and insert a new User record into the database.
    
    Args:
        db (Session): Active SQLAlchemy database session.
        email (str): The email address for the user (must be unique).
        hashed_password (str): Hashed password string for user login.
        full_name (Optional[str]): Optional display name of the user.
        is_admin (bool): Boolean flag denoting administrative privileges.
        
    Returns:
        User: The newly created User SQLAlchemy model instance.
    """
    user = User(
        email=email,
        hashed_password=hashed_password,
        full_name=full_name,
        is_admin=is_admin
    )
    db.add(user)
    db.flush()
    return user

def get_user_preferences(db: Session, user_id: int) -> Optional[UserPreferences]:
    """
    Retrieve the Search Intent Preferences profile for a specific user.
    
    Args:
        db (Session): Active SQLAlchemy database session.
        user_id (int): The primary key ID of the user.
        
    Returns:
        Optional[UserPreferences]: The UserPreferences model instance if found, otherwise None.
    """
    return db.query(UserPreferences).filter(UserPreferences.user_id == user_id).first()

def create_user_preferences(db: Session, user_id: int) -> UserPreferences:
    """
    Initialize a default UserPreferences record linked to a new user.
    
    Args:
        db (Session): Active SQLAlchemy database session.
        user_id (int): The primary key ID of the user.
        
    Returns:
        UserPreferences: The created UserPreferences instance with default settings.
    """
    prefs = UserPreferences(
        user_id=user_id,
        onboarding_status="not_started",
        onboarding_history=[],
        question_count=0,
        confidence=0.0,
        profile_json=None
    )
    db.add(prefs)
    db.flush()
    return prefs

def update_user_preferences(
    db: Session, 
    user_id: int, 
    onboarding_status: Optional[str] = None,
    onboarding_history: Optional[list] = None,
    question_count: Optional[int] = None,
    confidence: Optional[float] = None,
    profile_json: Optional[dict] = None
) -> Optional[UserPreferences]:
    """
    Modify an existing UserPreferences profile for onboarding and configuration changes.
    
    Args:
        db (Session): Active SQLAlchemy database session.
        user_id (int): The primary key ID of the user.
        onboarding_status (Optional[str]): New onboarding status ("not_started", "in_progress", "completed").
        onboarding_history (Optional[list]): List of onboarding chat message dictionaries.
        question_count (Optional[int]): Number of dynamic onboarding questions asked.
        confidence (Optional[float]): Onboarding profile understanding confidence (0.0 to 1.0).
        profile_json (Optional[dict]): Structured search preferences configurations dictionary.
        
    Returns:
        Optional[UserPreferences]: Updated UserPreferences instance, or None if user preferences don't exist.
    """
    prefs = get_user_preferences(db, user_id=user_id)
    if not prefs:
        return None
    
    if onboarding_status is not None:
        prefs.onboarding_status = onboarding_status
    if onboarding_history is not None:
        prefs.onboarding_history = onboarding_history
    if question_count is not None:
        prefs.question_count = question_count
    if confidence is not None:
        prefs.confidence = confidence
    if profile_json is not None:
        prefs.profile_json = profile_json
        
    db.commit()
    return prefs
