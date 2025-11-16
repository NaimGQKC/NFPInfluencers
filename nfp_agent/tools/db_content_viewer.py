"""
Database Content Viewer
This utility prints the key columns from the 'public_content' table, 
joining it with the 'targets' table for readability.

Run this to verify what data the collector agents have stored.

Usage:
python -m nfp_agent.tools.db_content_viewer
"""
import sqlite3
import logging
import sys
import os

# Use relative imports to access core modules
try:
    from ..core import config, database
except ImportError:
    # Fallback for direct script execution outside the module structure
    sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
    from nfp_agent.core import config, database

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def view_all_content():
    """
    Fetches and prints key details for all scraped content.
    """
    logging.info("--- Fetching all scraped content from database ---")

    # SQL to join content with target usernames
    sql = """
    SELECT 
        t.username, 
        pc.platform, 
        pc.content_type, 
        pc.post_id, 
        pc.post_url,
        pc.media_url,
        pc.content_text
    FROM public_content pc
    JOIN targets t ON pc.target_id = t.id
    ORDER BY pc.scraped_at DESC
    LIMIT 20 
    """ # Limiting to 20 for screen readability

    conn = None
    try:
        conn = database.get_db_connection()
        cursor = conn.cursor()
        cursor.execute(sql)
        content_rows = cursor.fetchall()

        if not content_rows:
            logging.warning("No content found in the 'public_content' table.")
            return

        logging.info(f"Found {len(content_rows)} most recent content entries.")
        
        # --- Print Results ---
        print("\n" + "="*80)
        print("Scraped Content Summary (Last 20 Entries)")
        print("="*80)

        for i, row in enumerate(content_rows):
            print(f"[{i+1:02d}] TARGET: {row['username']} ({row['platform']})")
            print(f"      TYPE: {row['content_type']}")
            # Truncate text and URL for clean display
            text_snippet = (row['content_text'][:50] + '...') if row['content_text'] and len(row['content_text']) > 50 else row['content_text']
            url_snippet = (row['media_url'][:70] + '...') if row['media_url'] and len(row['media_url']) > 70 else row['media_url']

            print(f"      ID:   {row['post_id']} | URL: {row['post_url']}")
            print(f"      MEDIA URL (Crucial!): {url_snippet}")
            print(f"      CAPTION: {text_snippet}")
            print("-" * 80)
            
        print("Content fetch complete.")

    except sqlite3.OperationalError as e:
        if "no such table" in str(e):
            logging.error("Database tables not initialized. Did you run 'python -m nfp_agent.main init_db'?")
        else:
            logging.error(f"SQLite Error: {e}")
    except Exception as e:
        logging.error(f"An unexpected error occurred: {e}", exc_info=True)
    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    view_all_content()