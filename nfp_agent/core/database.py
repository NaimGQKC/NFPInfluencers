import logging
from supabase import create_client, Client
from . import config
import secrets
import string
import datetime

# --- NEW: Initialize Supabase Client ---
supabase: Client = None
if config.SUPABASE_URL and config.SUPABASE_KEY:
    supabase = create_client(config.SUPABASE_URL, config.SUPABASE_KEY)
else:
    logging.error("FATAL: Supabase URL or Service Role Key not configured.")
# --- END NEW ---

def get_db_connection():
    """
    Returns the initialized Supabase client.
    (This replaces the old sqlite3 get_db_connection)
    """
    if not supabase:
        raise Exception("Supabase client is not initialized.")
    return supabase

def init_db():
    """
    Supabase manages the schema. This function just confirms connection.
    (This replaces the old sqlite3 init_db)
    """
    logging.info("Connecting to Supabase to check tables...")
    try:
        db = get_db_connection()
        # Test connection by listing tables
        db.table('targets').select('id').limit(1).execute()
        logging.info("Database connection successful. 'targets' table is accessible.")
    except Exception as e:
        logging.error(f"Error connecting to Supabase or finding tables: {e}")
        logging.error("Please ensure your Supabase schema is migrated (see 'project/supabase/migrations')")

def generate_dossier_id():
    """
    Generates a secure, random 12-character ID for the dossier URL.
    Matches the frontend utility function [cite: `project/lib/supabase.ts`].
    """
    chars = string.ascii_letters + string.digits
    return ''.join(secrets.choice(chars) for _ in range(12))

def add_target(username: str, platform: str = "instagram") -> dict:
    """
    Adds a new influencer to the 'targets' table.
    Matches the frontend API logic [cite: `project/app/api/targets/route.ts`].
    Returns the new target object or existing target.
    (This replaces the old sqlite3 add_target)
    """
    if platform != "instagram":
        logging.warning("Only 'instagram' platform is supported for now.")
        return None

    db = get_db_connection()
    
    # Normalize username
    clean_username = username.strip().lower().replace('@', '')
    
    try:
        # Check if target already exists
        existing = db.table('targets').select('id, dossier_id, username').eq('username', clean_username).maybe_single().execute()
        
        if existing.data:
            logging.warning(f"Target '{clean_username}' already exists. Returning existing dossier.")
            return existing.data

        # If not, create new target with a unique dossier_id
        dossier_id = generate_dossier_id()
        
        new_target = db.table('targets').insert({
            'username': clean_username,
            'dossier_id': dossier_id,
            'last_updated_at': datetime.datetime.now(datetime.timezone.utc).isoformat()
        }).select('*').single().execute()

        logging.info(f"Successfully added target: {clean_username} (Dossier ID: {dossier_id})")
        return new_target.data
    
    except Exception as e:
        logging.error(f"Error adding target {clean_username}: {e}")
        return None

def list_targets() -> list:
    """
    Fetches all targets from the Supabase 'targets' table.
    (This replaces the old sqlite3 list_targets)
    """
    db = get_db_connection()
    try:
        response = db.table('targets').select('*').order('created_at', desc=True).execute()
        return response.data
    except Exception as e:
        logging.error(f"Error listing targets: {e}")
        return []

def get_target_by_name(username: str) -> dict:
    """
    Fetches a single target by their username.
    (This replaces the old sqlite3 get_target_by_name)
    """
    db = get_db_connection()
    clean_username = username.strip().lower().replace('@', '')
    try:
        response = db.table('targets').select('*').eq('username', clean_username).maybe_single().execute()
        return response.data
    except Exception as e:
        logging.error(f"Error getting target {clean_username}: {e}")
        return None

def content_exists(story_id: str) -> bool:
    """
    Checks if a specific story_id is already in the 'stories' table.
    (This replaces the old sqlite3 content_exists)
    """
    db = get_db_connection()
    try:
        # Use 'story_id' column from your schema [cite: `project/supabase/migrations/20251116235429_create_leviproof_schema.sql`]
        response = db.table('stories').select('id').eq('story_id', story_id).limit(1).execute()
        return bool(response.data)
    except Exception as e:
        logging.error(f"Error checking if content exists {story_id}: {e}")
        return False

def save_story(target_id_uuid: str, story_id: str, timestamp: str, media_type: str, media_url: str):
    """
    Saves a single story to the 'stories' table.
    Matches the Supabase schema [cite: `project/supabase/migrations/20251116235429_create_leviproof_schema.sql`].
    (This replaces the old sqlite3 save_content)
    """
    db = get_db_connection()
    try:
        db.table('stories').insert({
            'target_id': target_id_uuid,
            'story_id': story_id,
            'timestamp': timestamp,
            'media_type': media_type,
            'media_url': media_url, # Save the public URL
            'summary': None, # Will be filled by investigator
            'full_analysis': None # Will be filled by investigator
        }).execute()
        
        # Also update the parent target's last_updated_at
        db.table('targets').update({
            'last_updated_at': datetime.datetime.now(datetime.timezone.utc).isoformat()
        }).eq('id', target_id_uuid).execute()
        
    except Exception as e:
        if "unique constraint" in str(e).lower():
            logging.warning(f"Story with story_id {story_id} already exists. Skipping save.")
        else:
            logging.error(f"Error saving story {story_id}: {e}")

def update_story_analysis(story_id: str, summary: str, full_analysis: str):
    """
    Updates a story with the AI-generated analysis.
    (This is a new function for the investigator)
    """
    db = get_db_connection()
    try:
        db.table('stories').update({
            'summary': summary,
            'full_analysis': full_analysis
        }).eq('story_id', story_id).execute()
        
        # Update the parent target's last_updated_at timestamp
        # Find the target_id from the story
        story = db.table('stories').select('target_id').eq('story_id', story_id).single().execute()
        if story.data:
            db.table('targets').update({
                'last_updated_at': datetime.datetime.now(datetime.timezone.utc).isoformat()
            }).eq('id', story.data['target_id']).execute()

        logging.info(f"Successfully updated analysis for story {story_id}")
    except Exception as e:
        logging.error(f"Error updating analysis for story {story_id}: {e}")