from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, func, JSON, Float, Boolean
from sqlalchemy.orm import relationship
from app.database import Base

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

    # One-to-one relationship with LeadAnalysis
    analysis = relationship("LeadAnalysis", back_populates="post", uselist=False, cascade="all, delete-orphan")


class LeadAnalysis(Base):
    __tablename__ = "lead_analysis"

    id = Column(Integer, primary_key=True, index=True)
    post_id = Column(Integer, ForeignKey("reddit_posts.id", ondelete="CASCADE"), unique=True, nullable=False)
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
    analyzed_at = Column(DateTime, server_default=func.now())

    post = relationship("RedditPost", back_populates="analysis")


class UserPreferences(Base):
    __tablename__ = "user_preferences"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, unique=True, index=True, default=1, nullable=False)
    onboarding_status = Column(String(50), default="not_started", nullable=False)  # not_started, in_progress, completed
    onboarding_history = Column(JSON, default=list, nullable=True)  # Stores chat history list
    question_count = Column(Integer, default=0, nullable=False)
    confidence = Column(Float, default=0.0, nullable=False)
    profile_json = Column(JSON, nullable=True)  # Stores the final Search Intent Profile JSON


