from pydantic import BaseModel, EmailStr
from typing import Optional, List

class UserRegister(BaseModel):
    email: EmailStr
    password: str
    full_name: Optional[str] = None

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class Token(BaseModel):
    access_token: str
    token_type: str
    is_admin: bool

class OnboardingResponse(BaseModel):
    response: str

class StatusUpdate(BaseModel):
    status: str  # New, Replied, Interested, Won, Lost

class NoteCreate(BaseModel):
    text: str

class MonitoredSubredditsUpdate(BaseModel):
    subreddits: str

class PromptsUpdate(BaseModel):
    analyzer_instructions: Optional[str] = None
    onboarding_instructions: Optional[str] = None
