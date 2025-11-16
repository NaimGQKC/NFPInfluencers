import os
from dotenv import load_dotenv
from pathlib import Path
import sys
import logging

# --- Path Setup ---
BASE_DIR = Path(__file__).parent.parent.parent
env_path = BASE_DIR / '.env'
load_dotenv(dotenv_path=env_path)

# --- Define Settings ---
DB_PATH_STR = str(BASE_DIR / "data" / "surveillance.db")
LOG_FILE_PATH = BASE_DIR / "data" / "agent.log"
AUTH_FILE = BASE_DIR / "auth.json" # Instagram auth file

# Gemini API
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Proxy
PROXY_URL = os.getenv("PROXY_URL") # e.g., "http://user:pass@host:port"

# Dropbox
DROPBOX_FILE_REQUEST_URL = os.getenv("DROPBOX_FILE_REQUEST_URL")

# Reddit
REDDIT_CLIENT_ID = os.getenv("REDDIT_CLIENT_ID")
REDDIT_CLIENT_SECRET = os.getenv("REDDIT_CLIENT_SECRET")
REDDIT_USERNAME = os.getenv("REDDIT_USERNAME")
REDDIT_PASSWORD = os.getenv("REDDIT_PASSWORD")
REDDIT_USER_AGENT = "NFPInfluencers Agent v0.1 by u/NaimGQKC"

# Instagram
IG_USERNAME = os.getenv("IG_USERNAME")
IG_PASSWORD = os.getenv("IG_PASSWORD")
IG_APP_ID = os.getenv("IG_APP_ID")
# --- Validation Function (Now with arguments) ---
def validate_config(required_keys: list = None):
    """Checks that all essential keys are loaded."""
    logging.info("Validating configuration...")
    errors = []
    
    # --- THIS IS THE FIX ---
    # If no specific keys are requested, check the general ones.
    # If specific keys ARE requested, only check those.
    
    if required_keys is None:
        # General check for all tools
        if not DROPBOX_FILE_REQUEST_URL or "YOUR_DROPBOX_LINK" in DROPBOX_FILE_REQUEST_URL:
            errors.append("DROPBOX_FILE_REQUEST_URL is not set in .env")
        if not GEMINI_API_KEY or "YOUR_GEMINI" in GEMINI_API_KEY:
            errors.append("GEMINI_API_KEY is not set in .env")
    else:
        if "IG_USERNAME" in required_keys and (not IG_USERNAME or "your_burner_ig_username" in IG_USERNAME):
            errors.append("IG_USERNAME is not set in .env")
        if "IG_PASSWORD" in required_keys and (not IG_PASSWORD or "your_burner_ig_password" in IG_PASSWORD):
            errors.append("IG_PASSWORD is not set in .env")
        # --- ADD THIS ---
        if "IG_APP_ID" in required_keys and (not IG_APP_ID or "YOUR_IG_APP_ID_HERE" in IG_APP_ID):
            errors.append("IG_APP_ID is not set in .env. Get this from browser dev tools.")
        # --- END ADDITION ---
        if "REDDIT_CLIENT_ID" in required_keys and (not REDDIT_CLIENT_ID or "YOUR_REDDIT" in REDDIT_CLIENT_ID):            errors.append("REDDIT_CLIENT_ID is not set in .env")

    if not errors:
        logging.info("Configuration loaded successfully.")
        return True
    else:
        logging.error("--- CONFIGURATION ERRORS ---")
        for error in errors:
            logging.error(f"- {error}")
        logging.error("Please fill out your .env file before proceeding.")
        logging.error("------------------------------")
        sys.exit(1) # Exit the script if config is invalid

if __name__ == "__main__":
    validate_config()