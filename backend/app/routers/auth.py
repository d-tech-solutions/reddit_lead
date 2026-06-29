from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
import httpx
import logging
import secrets

from app.database import get_db
from app.models import User
from app.schemas import UserRegister, UserLogin, Token
from app.auth_service import (
    get_password_hash,
    verify_password,
    create_access_token,
    get_current_user
)
from app.config import settings
from app import crud

router = APIRouter(prefix="/auth", tags=["Authentication"])
logger = logging.getLogger(__name__)

@router.post('/register', response_model=Token)
def register(data: UserRegister, db: Session = Depends(get_db)):
    # Check if email is already taken
    existing_user = crud.get_user_by_email(db, data.email)
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email address is already registered."
        )
    
    # Hash password and create user
    hashed_password = get_password_hash(data.password)
    user = crud.create_user(
        db, 
        email=data.email, 
        hashed_password=hashed_password, 
        full_name=data.full_name
    )
    
    # Initialize user preferences
    crud.create_user_preferences(db, user_id=user.id)
    db.commit()
    
    access_token = create_access_token(data={"sub": user.email})
    return {"access_token": access_token, "token_type": "bearer", "is_admin": user.is_admin}

@router.post('/login', response_model=Token)
def login(data: UserLogin, db: Session = Depends(get_db)):
    user = crud.get_user_by_email(db, data.email)
    if not user or not verify_password(data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    access_token = create_access_token(data={"sub": user.email})
    return {"access_token": access_token, "token_type": "bearer", "is_admin": user.is_admin}

@router.get('/me')
def get_me(current_user: User = Depends(get_current_user)):
    return {
        "id": current_user.id,
        "email": current_user.email,
        "full_name": current_user.full_name,
        "is_admin": current_user.is_admin,
        "created_at": current_user.created_at
    }

@router.get('/google')
def google_login():
    client_id = settings.GOOGLE_CLIENT_ID
    redirect_uri = settings.GOOGLE_REDIRECT_URI
    if not client_id:
        raise HTTPException(
            status_code=400, 
            detail="Google Client ID is not configured in .env."
        )
    
    scope = "openid email profile"
    auth_url = (
        f"https://accounts.google.com/o/oauth2/v2/auth?"
        f"client_id={client_id}&"
        f"redirect_uri={redirect_uri}&"
        f"response_type=code&"
        f"scope={scope}"
    )
    return {"url": auth_url}

@router.get('/google/callback')
async def google_callback(code: str = None, db: Session = Depends(get_db)):
    if not code:
        raise HTTPException(status_code=400, detail="OAuth authorization code not provided.")
    
    client_id = settings.GOOGLE_CLIENT_ID
    client_secret = settings.GOOGLE_CLIENT_SECRET
    redirect_uri = settings.GOOGLE_REDIRECT_URI
    
    token_url = "https://oauth2.googleapis.com/token"
    data = {
        "code": code,
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code"
    }
    
    try:
        async with httpx.AsyncClient() as client:
            token_response = await client.post(token_url, data=data, timeout=10.0)
            token_response.raise_for_status()
            token_json = token_response.json()
            access_token = token_json.get("access_token")
            
            userinfo_url = "https://www.googleapis.com/oauth2/v3/userinfo"
            headers = {"Authorization": f"Bearer {access_token}"}
            userinfo_response = await client.get(userinfo_url, headers=headers, timeout=10.0)
            userinfo_response.raise_for_status()
            user_info = userinfo_response.json()
            
        email = user_info.get("email")
        full_name = user_info.get("name", "")
        
        if not email:
            raise HTTPException(status_code=400, detail="Google authentication did not provide an email.")
            
        # Find or create Google authenticated user
        user = crud.get_user_by_email(db, email)
        if not user:
            random_pw = secrets.token_hex(16)
            hashed_pw = get_password_hash(random_pw)
            user = crud.create_user(
                db, 
                email=email, 
                hashed_password=hashed_pw, 
                full_name=full_name
            )
            
            # Create user preferences
            crud.create_user_preferences(db, user_id=user.id)
            db.commit()
            
        jwt_token = create_access_token(data={"sub": user.email})
        
        # Redirect to frontend callback page
        return RedirectResponse(url=f"{settings.FRONTEND_URL}/auth/callback?token={jwt_token}")
        
    except Exception as e:
        logger.error(f"Google OAuth Callback failed: {e}", exc_info=True)
        return RedirectResponse(url=f"{settings.FRONTEND_URL}/login?error=oauth_failed")
