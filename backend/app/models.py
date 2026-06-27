from sqlalchemy import Column, Integer, String, Text, DateTime, func
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
