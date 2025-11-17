import os
from dotenv import load_dotenv
from pathlib import Path
import sys
import logging

# --- Path Setup ---
BASE_DIR = Path(__file__).parent.parent.parent
# --- MODIFIED: Load the .env from the root of the NFPInfluencers project ---
env_path = BASE_DIR / '.env'
load_dotenv(dotenv_path=env_path)

# --- Define Settings ---
# DE-SCOPED: We no longer use a local SQLite DB
# DB_PATH_STR = str(BASE_DIR / "data" / "surveillance.db") 
LOG_FILE_PATH = BASE_DIR / "data" / "agent.log"
AUTH_FILE = BASE_DIR / "auth.json" # Instagram auth file

# Gemini API
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# --- NEW: Supabase Config ---
# We get these values from the .env file
SUPABASE_URL = os.getenv("SUPABASE_URL")
# IMPORTANT: Use the SERVICE_ROLE_KEY for the backend, not the ANON_KEY
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY") 

# ... (Reddit, Instagram keys remain the same) ...
IG_USERNAME = os.getenv("IG_USERNAME")
IG_PASSWORD = os.getenv("IG_PASSWORD")
IG_APP_ID = os.getenv("IG_APP_ID")
# ... (rest of your keys) ...
REDDIT_CLIENT_ID = os.getenv("REDDIT_CLIENT_ID")
REDDIT_CLIENT_SECRET = os.getenv("REDDIT_CLIENT_SECRET")
REDDIT_USERNAME = os.getenv("REDDIT_USERNAME")
REDDIT_PASSWORD = os.getenv("REDDIT_PASSWORD")
REDDIT_USER_AGENT = "NFPInfluencers Agent v0.1 by u/NaimGQKC"


# --- Validation Function (Updated) ---
def validate_config(required_keys: list = None):
    """Checks that all essential keys are loaded."""
    logging.info("Validating configuration...")
    errors = []
    
    # General check
    if not GEMINI_API_KEY or "YOUR_GEMINI" in GEMINI_API_KEY:
        errors.append("GEMINI_API_KEY is not set in .env")
    
    # --- NEW: Check for Supabase keys ---
    if not SUPABASE_URL:
        errors.append("SUPABASE_URL is not set in .env")
    if not SUPABASE_KEY:
        # Check for either the service key (backend) or the anon key (frontend .env)
        if not os.getenv("SUPABASE_SERVICE_ROLE_KEY"):
            errors.append("SUPABASE_SERVICE_ROLE_KEY is not set in .env")

    if required_keys:
        if "IG_USERNAME" in required_keys and (not IG_USERNAME or "your_burner_ig_username" in IG_USERNAME):
            errors.append("IG_USERNAME is not set in .env")
        if "IG_PASSWORD" in required_keys and (not IG_PASSWORD or "your_burner_ig_password" in IG_PASSWORD):
            errors.append("IG_PASSWORD is not set in .env")
        if "IG_APP_ID" in required_keys and (not IG_APP_ID or "YOUR_IG_APP_ID_HERE" in IG_APP_ID):
            errors.append("IG_APP_ID is not set in .env")
        if "REDDIT_CLIENT_ID" in required_keys and (not REDDIT_CLIENT_ID or "YOUR_REDDIT" in REDDIT_CLIENT_ID):
            errors.append("REDDIT_CLIENT_ID is not set in .env")

    if not errors:
        logging.info("Configuration loaded successfully.")
        return True
    else:
        logging.error("--- CONFIGURATION ERRORS ---")
        for error in errors:
            logging.error(f"- {error}")
        logging.error("Please fill out your .env file before proceeding.")
        logging.error("------------------------------")
        sys.exit(1)

if __name__ == "__main__":
    validate_config()