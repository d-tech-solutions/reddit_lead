import logging
from datetime import datetime, timezone
import xml.etree.ElementTree as ET
import httpx
from sqlalchemy.orm import Session
from app.config import settings
from app import crud


logger = logging.getLogger(__name__)

# TODO: Migrate this public RSS feed fetching logic to the official Reddit API (PRAW) in the future.
def fetch_subreddit_posts(subreddit: str) -> list:
    url = f"https://www.reddit.com/r/{subreddit}/new.rss"
    headers = {
        # Unique and descriptive User-Agent as required by Reddit's API guidelines
        "User-Agent": "LeadRadarAI/1.0 (by /u/dharanidharan)"
    }
    
    try:
        logger.info(f"Fetching posts from r/{subreddit} RSS feed...")
        response = httpx.get(url, headers=headers, timeout=10.0)
        
        if response.status_code == 429:
            logger.warning(f"Reddit RSS rate limited (429) for r/{subreddit}")
            return []
            
        response.raise_for_status()
        
        # Parse Atom XML
        ns = {'atom': 'http://www.w3.org/2005/Atom'}
        root = ET.fromstring(response.content)
        
        posts = []
        for entry in root.findall('atom:entry', ns):
            entry_id = entry.find('atom:id', ns)
            if entry_id is None or not entry_id.text:
                continue
                
            # Extract Reddit ID (e.g. "t3_1d2x3y" -> "1d2x3y")
            reddit_id = entry_id.text.split('_')[-1] if '_' in entry_id.text else entry_id.text
            
            # Extract Title
            title_elem = entry.find('atom:title', ns)
            title = title_elem.text if title_elem is not None else "[No Title]"
            
            # Extract Content
            content_elem = entry.find('atom:content', ns)
            content = content_elem.text if content_elem is not None else ""
            
            # Extract Author
            author_elem = entry.find('atom:author', ns)
            author = ""
            if author_elem is not None:
                name_elem = author_elem.find('atom:name', ns)
                if name_elem is not None and name_elem.text:
                    author = name_elem.text.replace("/u/", "")
            
            # Extract URL
            link_elem = entry.find('atom:link', ns)
            url_str = link_elem.attrib.get('href') if link_elem is not None else ""
            
            # Extract Timestamp
            updated_elem = entry.find('atom:updated', ns)
            if updated_elem is not None and updated_elem.text:
                try:
                    created_utc = datetime.fromisoformat(updated_elem.text).replace(tzinfo=None)
                except Exception:
                    created_utc = datetime.now(timezone.utc).replace(tzinfo=None)
            else:
                created_utc = datetime.now(timezone.utc).replace(tzinfo=None)
                
            posts.append({
                "reddit_id": reddit_id,
                "title": title,
                "content": content,
                "author": author,
                "subreddit": subreddit,
                "url": url_str,
                "created_utc": created_utc
            })
        return posts
    except Exception as e:
        logger.error(f"Error fetching posts from r/{subreddit}: {e}", exc_info=True)
        return []

def collect_leads(db: Session) -> dict:
    subreddits = settings.subreddit_list
    total_fetched = 0
    total_saved = 0
    
    for sub in subreddits:
        posts = fetch_subreddit_posts(sub)
        total_fetched += len(posts)
        
        for post in posts:
            # Check if post already exists in the database
            exists = crud.get_post_by_reddit_id(db, reddit_id=post["reddit_id"])
            if not exists:
                crud.create_reddit_post(db, post)

                total_saved += 1
        
        try:
            db.commit()
        except Exception as e:
            db.rollback()
            logger.error(f"Error saving posts for r/{sub}: {e}", exc_info=True)
            
    logger.info(f"Collection cycle complete. Fetched {total_fetched} posts, saved {total_saved} new posts.")
    return {
        "fetched": total_fetched,
        "saved": total_saved
    }
