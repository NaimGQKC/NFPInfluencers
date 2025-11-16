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
# We still use LangChain for the *analysis* part
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import StrOutputParser

# --- GLOBAL YAML CONFIG PATH ---
YAML_CONFIG_PATH = Path(__file__).parent / "legal_provisions.yaml"

# --- Media Download Config ---
MEDIA_DIR = config.BASE_DIR / "data" / "media"
os.makedirs(MEDIA_DIR, exist_ok=True)

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

def _load_rag_context(config_data: dict) -> str:
    """
    Returns the REAL legal context from the loaded YAML data.
    """
    logging.info("Loading REAL legal context (RAG) from YAML...")
    return config_data['legal_context']

# --- NEW: Real Transcription Function (using Gemini) ---
def _transcribe_video_real(post_id: str, media_url: str) -> str:
    """
    Downloads a video and transcribes it using the Gemini API.
    Returns the transcribed text.
    """
    if not genai:
        logging.error("Gemini API not configured. Skipping transcription.")
        return "[Transcription Failed: API not configured]"
        
    logging.info(f"Starting transcription for {post_id}...")
    
    # We use .mp4 extension for all videos, regardless of original type
    video_path = MEDIA_DIR / f"{post_id}.mp4" 
    
    try:
        # --- 1. Download Video ---
        if not os.path.exists(video_path):
            logging.info(f"  > Downloading video: {media_url}")
            # Use httpx with follow_redirects for CDN links
            with httpx.stream("GET", media_url, timeout=30.0, follow_redirects=True) as response:
                response.raise_for_status() 
                with open(video_path, "wb") as f:
                    for chunk in response.iter_bytes():
                        f.write(chunk)
            logging.info(f"  > Video saved to: {video_path}")
        else:
            logging.info(f"  > Video already downloaded: {video_path}")

        # --- 2. Upload and Transcribe with Gemini ---
        logging.info("  > Uploading video to Gemini for transcription...")
        
        # Uploads the file to the Gemini API (temporary file)
        video_file = genai.upload_file(path=video_path, display_name=post_id)
        logging.info("  > Upload complete. Waiting for transcription...")

        # Transcribe with Gemini 2.5 Flash
        model = genai.GenerativeModel(model_name="gemini-2.5-flash")
        
        response = model.generate_content([
            "Transcribe the audio from this video. Only return the full, raw transcript and nothing else.",
            video_file
        ])
        
        # Clean up the temporary file from Google's side immediately
        genai.delete_file(video_file.name)

        transcript = response.text.strip()
        if not transcript:
            transcript = "[Transcription empty or video has no audio]"
            
        logging.info(f"  > Transcription complete for {post_id}.")
        return transcript

    except httpx.RequestError as e:
        logging.error(f"  > Download failed for {post_id}: {e}")
        return "[Transcription Failed: Download error]"
    except Exception as e:
        logging.error(f"  > An unknown transcription error occurred for {post_id}: {e}")
        return f"[Transcription Failed: {e}]"

def run_investigation(target_username: str):
    """
    The main entry point for the Investigator Agent.
    """
    logging.info(f"--- Starting Investigation for: {target_username} ---")
    
    # 1. Validate Config & Load YAML
    if not config.GEMINI_API_KEY:
        logging.error("GEMINI_API_KEY not configured. Exiting.")
        return
        
    config_data = _load_yaml_config() 

    # 2. Initialize LangChain LLM (for RAG analysis)
    llm = ChatGoogleGenerativeAI(
        model="gemini-2.5-flash", 
        temperature=0.1,
        google_api_key=config.GEMINI_API_KEY
    )

    # 3. Load RAG context (our legal documents)
    legal_context = _load_rag_context(config_data)

    # 4. Get Target and Content from DB
    target = database.get_target_by_name(target_username)
    if not target:
        logging.error(f"No target found with username: {target_username}")
        return
        
    content_list = _get_content_for_target(target['id'])
    if not content_list:
        logging.info("No content to investigate.")
        return

    # 5. Define the LangChain RAG Prompt
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

    # 6. Create the LangChain "Chain"
    chain = prompt | llm | StrOutputParser()

    # 7. Iterate, Transcribe, and Analyze
    logging.info(f"--- Analyzing {len(content_list)} pieces of content ---")
    
    output_dir = config.BASE_DIR / "data" / "investigations" / target_username
    os.makedirs(output_dir, exist_ok=True)
    logging.info(f"Output folder created at: {output_dir}")

    for content in content_list:
        post_id = content['post_id']
        logging.info(f"Investigating post: {post_id} ({content['post_url']}) (Type: {content['content_type']})")
        
        caption = content['content_text']
        transcript = "[Media is an image, no audio.]" # Default

        content_type = content['content_type']
        media_url = content['media_url']
        
        # --- NEW TRANSCRIPTION LOGIC ---
        if content_type == 'story_video' or (media_url and '.mp4' in media_url):
            logging.info("  > Video media detected. Attempting transcription...")
            # This now calls the Gemini API transcribe function
            transcript = _transcribe_video_real(post_id, media_url)
        else:
            logging.info("  > No video media detected. Skipping transcription.")
        # --- END NEW LOGIC ---

        # Run the RAG analysis chain
        try:
            result = chain.invoke({
                "context": legal_context,
                "transcript": transcript,
                "caption": caption if caption else "[No caption]"
            })
            
            timestamp = datetime.datetime.now().strftime("%Y%M%d_%H%M%S")
            output_file = output_dir / f"analysis_{post_id}_{timestamp}.txt"
            
            with open(output_file, "w", encoding="utf-8") as f:
                f.write(result)
            logging.info(f"  > Analysis saved to: {output_file}")

        except Exception as e:
            logging.error(f"  > Failed to analyze post {post_id}: {e}")

    logging.info(f"--- Investigation complete for: {target_username} ---")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    if len(sys.argv) > 1:
        target_username = sys.argv[1]
        run_investigation(target_username)
    else:
        print("Please provide a target_username to investigate.")
        print("Usage: python -m nfp_agent.agents.investigator_agent [username]")