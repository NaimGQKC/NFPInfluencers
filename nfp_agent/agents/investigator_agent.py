import logging
import sys
import json
import os
import datetime
from pathlib import Path 
import yaml 
import httpx
import google.generativeai as genai
from ..core import config, database 

# --- LangChain & Gemini Imports ---
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import StrOutputParser

# --- GLOBAL YAML CONFIG PATH ---
YAML_CONFIG_PATH = Path(__file__).parent / "legal_provisions.yaml"

# --- DE-SCOPED: We no longer save analysis to local files ---
# INVESTIGATION_DIR = config.BASE_DIR / "data" / "investigations"
# os.makedirs(INVESTIGATION_DIR, exist_ok=True)

if config.GEMINI_API_KEY:
    genai.configure(api_key=config.GEMINI_API_KEY)
else:
    logging.warning("GEMINI_API_KEY not found. Transcription and analysis will fail.")

def _load_yaml_config():
    """Loads the legal provisions from the YAML file."""
    try:
        with open(YAML_CONFIG_PATH, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    except Exception as e:
        logging.error(f"FATAL: Error loading YAML config: {e}")
        sys.exit(1)

def _get_unanalyzed_stories() -> list:
    """
    Helper function to query Supabase for video stories
    that have not been analyzed yet.
    """
    logging.info("Querying database for unanalyzed stories...")
    db = database.get_db_connection()
    try:
        # Find stories where full_analysis is null
        # Joins with targets to get username
        response = db.table('stories').select('*, targets(username)') \
            .eq('media_type', 'video') \
            .is_('full_analysis', 'null') \
            .execute()
        
        logging.info(f"Found {len(response.data)} new video items to analyze.")
        return response.data
    except Exception as e:
        logging.error(f"Error querying for unanalyzed stories: {e}")
        return []

def _load_rag_context(config_data: dict) -> str:
    """
    Returns the REAL legal context from the loaded YAML data.
    """
    logging.info("Loading REAL legal context (RAG) from YAML...")
    return config_data['legal_context']

def _transcribe_video_from_url(story_id: str, media_url: str) -> str:
    """
    Downloads a video *in-memory* from a URL and transcribes it.
    """
    if not genai:
        logging.error("Gemini API not configured. Skipping transcription.")
        return "[Transcription Failed: API not configured]"
        
    logging.info(f"Starting transcription for {story_id} from URL...")
    
    temp_video_path = None
    try:
        # --- 1. Download Video to a temporary file ---
        # We must download it, as Gemini can't transcribe from a URL directly
        temp_video_path = Path(f"temp_video_{story_id}.mp4")
        
        with httpx.stream("GET", media_url, timeout=30.0, follow_redirects=True) as response:
            response.raise_for_status() 
            with open(temp_video_path, "wb") as f:
                for chunk in response.iter_bytes():
                    f.write(chunk)
        
        logging.info(f"  > Temp video saved to: {temp_video_path}")

        # --- 2. Upload and Transcribe with Gemini ---
        logging.info(f"  > Uploading {temp_video_path} to Gemini for transcription...")
        
        video_file = genai.upload_file(path=temp_video_path, display_name=story_id)
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
            
        logging.info(f"  > Transcription complete for {story_id}.")
        return transcript

    except httpx.RequestError as e:
        logging.error(f"  > Download failed for {story_id}: {e}")
        return "[Transcription Failed: Download error]"
    except Exception as e:
        logging.error(f"  > An unknown transcription error occurred for {story_id}: {e}")
        return f"[Transcription Failed: {e}]"
    finally:
        # --- 3. Clean up the temporary file ---
        if temp_video_path and temp_video_path.exists():
            os.remove(temp_video_path)
            logging.info(f"  > Cleaned up temp file: {temp_video_path}")

def analyze_content_item(story: dict, llm: ChatGoogleGenerativeAI, legal_context: str):
    """
    Runs the analysis for a single story item from Supabase.
    """
    story_id = story['story_id']
    media_url = story['media_url']
    
    logging.info(f"Investigating story: {story_id} (Type: {story['media_type']})")
    
    transcript = "[Media is an image, no audio.]" # Default

    if story['media_type'] == 'video':
        logging.info("  > Video media detected. Attempting transcription...")
        transcript = _transcribe_video_from_url(story_id, media_url)
    else:
        # This function should only be called on videos, but as a safeguard
        logging.info("  > Image media. Skipping transcription.")
        # We still save "No violations found" to mark it as "processed"
        transcript = "[Media is an image, no audio.]"

    # --- RAG ANALYSIS ---
    prompt_template = """
    ROLE: You are a senior compliance analyst for the Ontario Securities Commission (OSC)
    and Competition Bureau of Canada. Your task is to identify specific,
    citable violations in promotional content.

    TASK: Analyze the provided EVIDENCE (video transcript)
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

    FINDINGS (Return ONLY your analysis):
    """
    
    prompt = PromptTemplate(
        input_variables=["context", "transcript"],
        template=prompt_template
    )
    chain = prompt | llm | StrOutputParser()

    try:
        full_analysis = chain.invoke({
            "context": legal_context,
            "transcript": transcript,
        })
        
        # --- NEW: Generate a 1-sentence summary for the frontend ---
        # This matches the 'summary' field in the 'stories' table
        summary_prompt_text = f"Given the following analysis, write a 1-sentence summary of the finding (e.g., 'No violations found' or 'Found 2 violations of Misleading Performance Claims'). \n\nANALYSIS: {full_analysis}\n\nSUMMARY:"
        summary_chain = PromptTemplate.from_template(summary_prompt_text) | llm | StrOutputParser()
        summary = summary_chain.invoke({})
        
        # --- SAVE ANALYSIS TO SUPABASE ---
        database.update_story_analysis(
            story_id=story_id,
            summary=summary,
            full_analysis=full_analysis
        )

    except Exception as e:
        logging.error(f"  > Failed to analyze post {story_id}: {e}")

# --- REFACTORED: This is the original CLI function ---
def run_investigation_for_target(target_username: str):
    """
    The main entry point for the Investigator Agent CLI.
    Analyzes ALL unanalyzed content for a given target.
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
    
    # --- MODIFIED: Get unanalyzed stories for *this specific target* ---
    db = database.get_db_connection()
    response = db.table('stories').select('*, targets!inner(username)') \
        .eq('media_type', 'video') \
        .is_('full_analysis', 'null') \
        .eq('targets.username', target_username) \
        .execute()
    
    content_list = response.data
    if not content_list:
        logging.info("No new content to investigate for this target.")
        return

    logging.info(f"--- Analyzing {len(content_list)} pieces of content ---")
    
    for story in content_list:
        analyze_content_item(story, llm, legal_context)

    logging.info(f"--- Investigation complete for: {target_username} ---")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    if len(sys.argv) > 1:
        target_username = sys.argv[1]
        run_investigation_for_target(target_username)
    else:
        print("Please provide a target_username to investigate.")
        print("Usage: python -m nfp_agent.agents.investigator_agent [username]")