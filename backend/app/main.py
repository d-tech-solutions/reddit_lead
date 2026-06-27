from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import engine, Base, get_db
from app.models import RedditPost
from app.collector import collect_leads

# Initialize database tables on startup
Base.metadata.create_all(bind=engine)

app = FastAPI(title="LeadRadar AI Backend")

@app.get('/')
def home():
    return {
        "message": "Hello! This is Dharanidharan. LeadRadar AI is active."
    }

@app.get('/users')
def users():
    return [
        { "id": 1, "name": "Dharanidharan" },
        { "id": 2, "name": "DD" }
    ]

@app.post('/collector/trigger')
def trigger_collector(db: Session = Depends(get_db)):
    try:
        results = collect_leads(db)
        return {
            "status": "success",
            "message": "Reddit collection cycle completed",
            "details": results
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Collector failed: {str(e)}")

@app.get('/collector/posts')
def get_posts(limit: int = 50, db: Session = Depends(get_db)):
    posts = db.query(RedditPost).order_by(RedditPost.created_utc.desc()).limit(limit).all()
    return posts