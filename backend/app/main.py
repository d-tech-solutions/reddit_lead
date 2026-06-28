from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import engine, Base, get_db
from app.models import RedditPost, LeadAnalysis
from app.collector import collect_leads
from app.analyzer import analyze_pending_posts

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

@app.post('/leads/analyze')
def trigger_analysis(limit: int = 10, db: Session = Depends(get_db)):
    try:
        results = analyze_pending_posts(db, limit=limit)
        return {
            "status": "success",
            "message": "AI scoring cycle completed",
            "details": results
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")

@app.get('/leads')
def get_leads(min_score: int = 0, industry: str = None, limit: int = 50, db: Session = Depends(get_db)):
    query = db.query(RedditPost).join(LeadAnalysis).filter(LeadAnalysis.score >= min_score)
    if industry:
        query = query.filter(LeadAnalysis.industry.ilike(f"%{industry}%"))
    
    # Order by score descending to return highest quality opportunities first
    leads = query.order_by(LeadAnalysis.score.desc()).limit(limit).all()
    return leads

@app.get('/leads/{id}')
def get_lead_details(id: int, db: Session = Depends(get_db)):
    lead = db.query(RedditPost).filter(RedditPost.id == id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    return lead
