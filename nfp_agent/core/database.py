import sqlite3
from datetime import datetime
import os

# --- New Configuration ---
# Define the path for the database.
# This ensures it's always created in the 'data' folder
# relative to the project root.
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DB_PATH = os.path.join(BASE_DIR, "data", "surveillance.db")

def get_db_connection():
    """Creates a database connection."""
    # Ensure the 'data' directory exists
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Initializes the database and creates tables."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Table 1: Targets to track
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS targets (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT NOT NULL,
        platform TEXT NOT NULL,
        date_added TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(username, platform)
    );
    """)
    
    # Table 2: Public content (the evidence log)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS public_content (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        target_id INTEGER NOT NULL,
        platform TEXT NOT NULL,
        post_id TEXT NOT NULL,
        content_type TEXT NOT NULL, -- 'post', 'story', 'comment', 'reel'
        content_text TEXT,
        media_url TEXT,
        post_url TEXT,
        scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (target_id) REFERENCES targets (id),
        UNIQUE(post_id, platform)
    );
    """)
    
    conn.commit()
    conn.close()

def add_target(username: str, platform: str):
    """Adds a new target to the database."""
    conn = get_db_connection()
    try:
        conn.execute(
            "INSERT INTO targets (username, platform) VALUES (?, ?)",
            (username, platform)
        )
        conn.commit()
    except sqlite3.IntegrityError:
        print(f"Error: Target '{username}' on '{platform}' already exists.")
    finally:
        conn.close()

def list_targets():
    """Lists all targets in the database."""
    conn = get_db_connection()
    cursor = conn.execute("SELECT * FROM targets ORDER BY date_added DESC")
    targets = cursor.fetchall()
    conn.close()
    return targets

def save_content(
    target_id: int, 
    platform: str, 
    post_id: str, 
    content_type: str, 
    content_text: str, 
    media_url: str, 
    post_url: str
):
    """Saves a single piece of scraped content to the log."""
    conn = get_db_connection()
    try:
        conn.execute(
            """
            INSERT INTO public_content 
            (target_id, platform, post_id, content_type, content_text, media_url, post_url) 
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (target_id, platform, post_id, content_type, content_text, media_url, post_url)
        )
        conn.commit()
    except sqlite3.IntegrityError:
        # This is not an error, it just means we already logged this post.
        # print(f"Content {post_id} already exists.")
        pass 
    finally:
        conn.close()

def get_content_by_target(target_id: int):
    """Fetches all logged content for a specific target."""
    conn = get_db_connection()
    cursor = conn.execute(
        "SELECT * FROM public_content WHERE target_id = ? ORDER BY scraped_at DESC",
        (target_id,)
    )
    content = cursor.fetchall()
    conn.close()
    return content

# This part is removed, as main.py is now our *only* entrypoint
# if __name__ == "__main__":
#     init_db()