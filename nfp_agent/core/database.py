import sqlite3
import os
import datetime
import logging
from . import config # Use relative import

def get_db_connection():
    """
    Establishes a connection to the SQLite database.
    Creates the 'data' directory if it doesn't exist.
    Returns a connection object.
    """
    # Ensure the data directory exists
    db_dir = os.path.dirname(config.DB_PATH_STR)
    os.makedirs(db_dir, exist_ok=True)
    
    conn = sqlite3.connect(config.DB_PATH_STR)
    # Return rows as dictionaries
    conn.row_factory = sqlite3.Row 
    return conn

def init_db():
    """
    Initializes the database and creates the necessary tables 
    if they don't exist.
    """
    logging.info("Initializing database...")
    
    # SQL for creating the targets table
    create_targets_table = """
    CREATE TABLE IF NOT EXISTS targets (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT NOT NULL,
        platform TEXT NOT NULL,
        date_added TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(username, platform)
    );
    """
    
    # SQL for creating the public_content table
    # This schema matches what ig_scraper.py provides
    create_public_content_table = """
    CREATE TABLE IF NOT EXISTS public_content (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        target_id INTEGER NOT NULL,
        platform TEXT NOT NULL,
        post_id TEXT NOT NULL,
        content_type TEXT NOT NULL, -- 'post', 'reel', 'story', 'comment'
        content_text TEXT,
        media_url TEXT,
        post_url TEXT,
        author_username TEXT,
        scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (target_id) REFERENCES targets (id),
        UNIQUE(post_id, platform)
    );
    """

    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(create_targets_table)
        cursor.execute(create_public_content_table)
        conn.commit()
        logging.info("Database tables checked/created successfully.")
    except Exception as e:
        logging.error(f"Error initializing database: {e}")
    finally:
        conn.close()

def add_target(username: str, platform: str):
    """
    Adds a new influencer to the targets table.
    """
    sql = "INSERT INTO targets (username, platform) VALUES (?, ?)"
    
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(sql, (username, platform))
        conn.commit()
        logging.info(f"Successfully added target: {username} on {platform}")
    except sqlite3.IntegrityError:
        # This occurs if the UNIQUE(username, platform) constraint fails
        logging.warning(f"Error: Target '{username}' on '{platform}' already exists.")
    except Exception as e:
        logging.error(f"Error adding target {username}: {e}")
    finally:
        conn.close()

def list_targets() -> list:
    """
    Fetches all targets from the database, ordered by when they were added.
    Returns a list of dictionary-like Row objects.
    """
    sql = "SELECT * FROM targets ORDER BY date_added DESC"
    
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(sql)
        targets = cursor.fetchall()
        # Convert Row objects to plain dicts for easier use
        return [dict(row) for row in targets]
    except Exception as e:
        logging.error(f"Error listing targets: {e}")
        return []
    finally:
        conn.close()

def get_target_by_name(username: str) -> dict:
    """
    Fetches a single target by their username.
    Returns a dictionary-like Row object or None if not found.
    """
    sql = "SELECT * FROM targets WHERE username = ?"
    
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(sql, (username,))
        target = cursor.fetchone()
        return dict(target) if target else None
    except Exception as e:
        logging.error(f"Error getting target {username}: {e}")
        return None
    finally:
        conn.close()

def content_exists(post_id: str) -> bool:
    """
    Checks if a specific post_id is already in the public_content table.
    Returns True if it exists, False otherwise.
    """
    sql = "SELECT 1 FROM public_content WHERE post_id = ? LIMIT 1"
    
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(sql, (post_id,))
        exists = cursor.fetchone()
        return bool(exists)
    except Exception as e:
        logging.error(f"Error checking if content exists {post_id}: {e}")
        return False # Default to False on error
    finally:
        conn.close()

def save_content(target_id: int, platform: str, post_id: str, 
                 content_type: str, content_text: str, media_url: str, 
                 post_url: str, author_username: str):
    """
    Saves a single piece of scraped content to the public_content table.
    """
    sql = """
    INSERT INTO public_content 
    (target_id, platform, post_id, content_type, content_text, media_url, post_url, author_username) 
    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """
    
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(sql, (
            target_id, 
            platform, 
            post_id, 
            content_type, 
            content_text, 
            media_url, 
            post_url, 
            author_username
        ))
        conn.commit()
    except sqlite3.IntegrityError:
        logging.warning(f"Content with post_id {post_id} already exists. Skipping save.")
    except Exception as e:
        logging.error(f"Error saving content {post_id}: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    # This allows you to run `python -m nfp_agent.core.database` to init the DB
    logging.basicConfig(level=logging.INFO)
    print("Initializing database from direct script run...")
    init_db()
    print("Database initialization complete.")