from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, func, JSON, Float, Boolean, UniqueConstraint
from sqlalchemy.orm import relationship
from app.database import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    full_name = Column(String(255), nullable=True)
    is_admin = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, server_default=func.now())

    preferences = relationship("UserPreferences", back_populates="user", uselist=False, cascade="all, delete-orphan")
    analyses = relationship("LeadAnalysis", back_populates="user", cascade="all, delete-orphan")


class RedditPost(Base):
    __tablename__ = "reddit_posts"

    id = Column(Integer, primary_key=True, index=True)
    reddit_id = Column(String(100), unique=True, index=True, nullable=False)
    title = Column(String(500), nullable=False)
    content = Column(Text, nullable=True)
    author = Column(String(100), nullable=True)
    subreddit = Column(String(100), index=True, nullable=False)
    url = Column(String(1000), nullable=True)
    created_utc = Column(DateTime, nullable=False)
    collected_at = Column(DateTime, server_default=func.now())

    # One-to-many relationship with LeadAnalysis (since multiple users can analyze the same post)
    analyses = relationship("LeadAnalysis", back_populates="post", cascade="all, delete-orphan")


class LeadAnalysis(Base):
    __tablename__ = "lead_analysis"

    id = Column(Integer, primary_key=True, index=True)
    post_id = Column(Integer, ForeignKey("reddit_posts.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    relevant = Column(Boolean, default=False, nullable=False)
    score = Column(Integer, nullable=False)  # 0-100
    industry = Column(String(100), nullable=True)
    urgency = Column(String(50), nullable=True)  # Low, Medium, High
    intent = Column(String(200), nullable=True)
    estimated_budget = Column(String(100), nullable=True)
    recommended_service = Column(String(200), nullable=True)
    summary = Column(Text, nullable=True)
    suggested_reply = Column(Text, nullable=True)
    match_reasoning = Column(JSON, nullable=True)  # Stores a list of match reasons
    status = Column(String(50), default="New", nullable=False)  # New, Replied, Interested, Won, Lost
    saved = Column(Boolean, default=False, nullable=False)
    notes = Column(JSON, default=list, nullable=True)  # Stores list of notes
    analyzed_at = Column(DateTime, server_default=func.now())

    post = relationship("RedditPost", back_populates="analyses")
    user = relationship("User", back_populates="analyses")

    __table_args__ = (
        UniqueConstraint('post_id', 'user_id', name='uq_post_user'),
    )


class UserPreferences(Base):
    __tablename__ = "user_preferences"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), unique=True, index=True, nullable=False)
    onboarding_status = Column(String(50), default="not_started", nullable=False)  # not_started, in_progress, completed
    onboarding_history = Column(JSON, default=list, nullable=True)  # Stores chat history list
    question_count = Column(Integer, default=0, nullable=False)
    confidence = Column(Float, default=0.0, nullable=False)
    profile_json = Column(JSON, nullable=True)  # Stores the final Search Intent Profile JSON

    user = relationship("User", back_populates="preferences")



