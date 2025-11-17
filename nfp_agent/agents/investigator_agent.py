import logging
import sys
import json
import os
import datetime
from pathlib import Path 
import yaml 
import httpx # For downloading video
import google.generativeai as genai # NEW: For transcription
from ..core import config, database 

# --- LangChain & Gemini Imports ---
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import StrOutputParser

# --- GLOBAL YAML CONFIG PATH ---
YAML_CONFIG_PATH = Path(__file__).parent / "legal_provisions.yaml"

# --- Media Download Config ---
MEDIA_DIR = config.BASE_DIR / "data" / "media"
# --- THIS IS THE OUTPUT DIR FOR ANALYSIS FILES ---
INVESTIGATION_DIR = config.BASE_DIR / "data" / "investigations"
os.makedirs(MEDIA_DIR, exist_ok=True)
os.makedirs(INVESTIGATION_DIR, exist_ok=True)

# --- NEW: Configure the Gemini API client ---
if config.GEMINI_API_KEY:
    genai.configure(api_key=config.GEMINI_API_KEY)
else:
    logging.warning("GEMINI_API_KEY not found. Transcription and analysis will fail.")

def _load_yaml_config():
    """Loads the legal provisions from the YAML file."""
    try:
        with open(YAML_CONFIG_PATH, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    except FileNotFoundError:
        logging.error(f"FATAL: YAML config file not found at {YAML_CONFIG_PATH}")
        sys.exit(1)
    except yaml.YAMLError as exc:
        logging.error(f"FATAL: Error parsing YAML file: {exc}")
        sys.exit(1)

def _get_content_for_target(target_id: int) -> list:
    """
    Helper function to query the database for all content
    scraped from a specific target.
    """
    logging.info(f"Querying database for all content from target_id: {target_id}")
    sql = "SELECT * FROM public_content WHERE target_id = ?"
    
    conn = database.get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(sql, (target_id,))
        content_rows = cursor.fetchall()
        if not content_rows:
            logging.warning(f"No content found for target_id: {target_id}")
            return []
        
        logging.info(f"Found {len(content_rows)} pieces of content.")
        return [dict(row) for row in content_rows]
    except Exception as e:
        logging.error(f"Error querying content for target {target_id}: {e}")
        return []
    finally:
        conn.close()
        
# --- NEW MODULAR FUNCTION ---
def get_content_by_post_id(post_id: str) -> dict:
    """
    Fetches a single piece of content by its post_id.
    """
    sql = "SELECT * FROM public_content WHERE post_id = ? LIMIT 1"
    conn = database.get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(sql, (post_id,))
        row = cursor.fetchone()
        return dict(row) if row else None
    except Exception as e:
        logging.error(f"Error getting content for post_id {post_id}: {e}")
        return None
    finally:
        conn.close()

def _load_rag_context(config_data: dict) -> str:
    """
    Returns the REAL legal context from the loaded YAML data.
    """
    logging.info("Loading REAL legal context (RAG) from YAML...")
    return config_data['legal_context']

# --- REFACTORED: NO LONGER USES HTTPO ---
def _transcribe_video_real(post_id: str, media_path: str) -> str:
    """
    Reads a local video file and transcribes it using the Gemini API.
    Returns the transcribed text.
    """
    if not genai:
        logging.error("Gemini API not configured. Skipping transcription.")
        return "[Transcription Failed: API not configured]"
        
    logging.info(f"Starting transcription for {post_id} from local file: {media_path}")
    
    video_path = Path(media_path)
    
    try:
        if not video_path.exists():
            logging.error(f"  > File not found: {video_path}")
            return "[Transcription Failed: File not found]"

        # --- Upload and Transcribe with Gemini ---
        logging.info(f"  > Uploading {video_path} to Gemini for transcription...")
        
        video_file = genai.upload_file(path=video_path, display_name=post_id)
        logging.info("  > Upload complete. Waiting for transcription...")

        model = genai.GenerativeModel(model_name="gemini-2.5-flash")
        
        response = model.generate_content([
            "Transcribe the audio from this video. Only return the full, raw transcript and nothing else.",
            video_file
        ])
        
        genai.delete_file(video_file.name)

        transcript = response.text.strip()
        if not transcript:
            transcript = "[Transcription empty or video has no audio]"
            
        logging.info(f"  > Transcription complete for {post_id}.")
        return transcript

    except Exception as e:
        logging.error(f"  > An unknown transcription error occurred for {post_id}: {e}")
        return f"[Transcription Failed: {e}]"

# --- NEW MODULAR FUNCTION ---
def analyze_content_item(content: dict, llm: ChatGoogleGenerativeAI, legal_context: str, author_username: str):
    """
    Runs the analysis for a single piece of content.
    This is the core logic moved from run_investigation.
    """
    post_id = content['post_id']
    logging.info(f"Investigating post: {post_id} ({content['post_url']}) (Type: {content['content_type']})")
    
    caption = content['content_text']
    transcript = "[Media is an image, no audio.]" # Default

    content_type = content['content_type']
    media_path = content['media_url'] # This is the local file path
    
    # --- TRANSCRIPTION LOGIC ---
    if content_type == 'story_video' or (media_path and '.mp4' in media_path):
        logging.info("  > Video media detected. Attempting transcription...")
        transcript = _transcribe_video_real(post_id, media_path)
    else:
        logging.info("  > No video media detected. Skipping transcription.")

    # --- RAG ANALYSIS ---
    prompt_template = """
    ROLE: You are a senior compliance analyst for the Ontario Securities Commission (OSC)
    and Competition Bureau of Canada. Your task is to identify specific,
    citable violations in promotional content.

    TASK: Analyze the provided EVIDENCE (video transcript and caption)
    against the provided LEGAL CONTEXT. Identify all violations.
    For each violation, you MUST:
    1. State the violation (e.g., "Misleading Performance Claim").
    2. Provide the exact quote from the EVIDENCE.
    3. Cite the specific LEGAL CONTEXT that is being violated.
    
    If no violations are found, state "No violations found."

    ---
    LEGAL CONTEXT (from RAG):
    {context}
    ---
    EVIDENCE (Video Transcript):
    {transcript}
    ---
    EVIDENCE (Original Post Caption):
    {caption}
    ---

    FINDINGS (Return ONLY your analysis):
    """
    
    prompt = PromptTemplate(
        input_variables=["context", "transcript", "caption"],
        template=prompt_template
    )
    chain = prompt | llm | StrOutputParser()

    try:
        result = chain.invoke({
            "context": legal_context,
            "transcript": transcript,
            "caption": caption if caption else "[No caption]"
        })
        
        # --- SAVE ANALYSIS FILE ---
        output_dir = INVESTIGATION_DIR / author_username
        os.makedirs(output_dir, exist_ok=True)
        
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = output_dir / f"analysis_{post_id}_{timestamp}.txt"
        
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(result)
        logging.info(f"  > Analysis saved to: {output_file}")
        return output_file

    except Exception as e:
        logging.error(f"  > Failed to analyze post {post_id}: {e}")
        return None


# --- REFACTORED: This is the original CLI function ---
def run_investigation_for_target(target_username: str):
    """
    The main entry point for the Investigator Agent CLI.
    Analyzes ALL content for a given target.
    """
    logging.info(f"--- Starting Investigation for: {target_username} ---")
    
    if not config.GEMINI_API_KEY:
        logging.error("GEMINI_API_KEY not configured. Exiting.")
        return
        
    config_data = _load_yaml_config()
    llm = ChatGoogleGenerativeAI(
        model="gemini-2.5-flash", 
        temperature=0.1,
        google_api_key=config.GEMINI_API_KEY
    )
    legal_context = _load_rag_context(config_data)

    target = database.get_target_by_name(target_username)
    if not target:
        logging.error(f"No target found with username: {target_username}")
        return
        
    content_list = _get_content_for_target(target['id'])
    if not content_list:
        logging.info("No content to investigate.")
        return

    logging.info(f"--- Analyzing {len(content_list)} pieces of content ---")
    
    for content in content_list:
        analyze_content_item(content, llm, legal_context, target_username)

    logging.info(f"--- Investigation complete for: {target_username} ---")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    if len(sys.argv) > 1:
        target_username = sys.argv[1]
        # --- CLI now calls the refactored function ---
        run_investigation_for_target(target_username)
    else:
        print("Please provide a target_username to investigate.")
        print("Usage: python -m nfp_agent.agents.investigator_agent [username]")