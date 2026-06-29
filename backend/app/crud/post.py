from sqlalchemy.orm import Session
from typing import List, Optional
from app.models import RedditPost, LeadAnalysis

def get_post_by_reddit_id(db: Session, reddit_id: str) -> Optional[RedditPost]:
    """
    Retrieve a RedditPost record based on its unique external Reddit string ID.
    
    Args:
        db (Session): Active SQLAlchemy database session.
        reddit_id (str): The unique string identifier from Reddit (e.g. "t3_1d2x3y").
        
    Returns:
        Optional[RedditPost]: The RedditPost database model instance if found, otherwise None.
    """
    return db.query(RedditPost).filter(RedditPost.reddit_id == reddit_id).first()

def get_post_by_id(db: Session, post_id: int) -> Optional[RedditPost]:
    """
    Retrieve a RedditPost record from the database based on its unique primary key ID.
    
    Args:
        db (Session): Active SQLAlchemy database session.
        post_id (int): Unique primary key ID of the post.
        
    Returns:
        Optional[RedditPost]: The RedditPost database model instance if found, otherwise None.
    """
    return db.query(RedditPost).filter(RedditPost.id == post_id).first()

def create_reddit_post(db: Session, post_data: dict) -> RedditPost:
    """
    Construct and insert a new RedditPost record into the database.
    
    Args:
        db (Session): Active SQLAlchemy database session.
        post_data (dict): Dictionary containing post fields:
            - "reddit_id" (str): Unique Reddit ID.
            - "title" (str): Title of the Reddit post.
            - "content" (Optional[str]): Main content body of the post.
            - "author" (Optional[str]): Reddit username of the author.
            - "subreddit" (str): Name of the subreddit.
            - "url" (Optional[str]): Direct link to the Reddit thread.
            - "created_utc" (datetime): UTC timestamp when the post was created.
            
    Returns:
        RedditPost: The newly created RedditPost SQLAlchemy model instance.
    """
    post = RedditPost(
        reddit_id=post_data["reddit_id"],
        title=post_data["title"],
        content=post_data.get("content"),
        author=post_data.get("author"),
        subreddit=post_data["subreddit"],
        url=post_data.get("url"),
        created_utc=post_data["created_utc"]
    )
    db.add(post)
    return post

def get_pending_posts_for_user(db: Session, user_id: int, limit: int = 10) -> List[RedditPost]:
    """
    Find recently collected Reddit posts that do not yet have an associated LeadAnalysis entry
    specifically for the requesting user. Uses an outer join and checks for null values to isolate
    unevaluated posts.
    
    Args:
        db (Session): Active SQLAlchemy database session.
        user_id (int): Primary key ID of the user requesting matching.
        limit (int): Maximum number of records to return. Defaults to 10.
        
    Returns:
        List[RedditPost]: A list of RedditPost instances awaiting evaluation.
    """
    return (
        db.query(RedditPost)
        .outerjoin(
            LeadAnalysis, 
            (LeadAnalysis.post_id == RedditPost.id) & (LeadAnalysis.user_id == user_id)
        )
        .filter(LeadAnalysis.id == None)
        .order_by(RedditPost.created_utc.desc())
        .limit(limit)
        .all()
    )
