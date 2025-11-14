import logging
import sys
import json
import os
import datetime
from pathlib import Path 
import yaml 
from ..core import config, database 

# --- LangChain & Gemini Imports ---
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import StrOutputParser

# --- GLOBAL YAML CONFIG PATH ---
YAML_CONFIG_PATH = Path(__file__).parent / "legal_provisions.yaml"


def _load_yaml_config():
    """Loads the legal provisions and mock data from the YAML file."""
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
        # Convert sqlite3.Row objects to standard dicts
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

def _transcribe_video_mock(config_data: dict, media_url: str) -> str:
    """
    Returns a hard-coded "scam" transcript from the YAML data.
    """
    logging.warning(f"Using MOCK transcription for {media_url}")
    return config_data['mock_scam_transcript']

def run_investigation(target_username: str):
    """
    The main entry point for the Investigator Agent.
    - Loads RAG context (real) from YAML.
    - Gets content from the DB.
    - Transcribes videos (mock).
    - Analyzes text for violations using an LLM.
    - Saves analysis to a file.
    """
    logging.info(f"--- Starting Investigation for: {target_username} ---")
    
    # 1. Validate Config & Load YAML
    # NOTE: You must run `pip install -r requirements.txt` before running this,
    # as the `pyyaml` library is now required.
    if not config.validate_config(required_keys=["GEMINI_API_KEY"]):
        logging.error("GEMINI_API_KEY not configured. Exiting.")
        return
        
    config_data = _load_yaml_config() # Load all data from YAML

    # 2. Initialize LLM (Gemini 2.5 Flash for cost)
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
    
    # Create the output directory: data/investigations/[target_username]
    output_dir = config.BASE_DIR / "data" / "investigations" / target_username
    os.makedirs(output_dir, exist_ok=True)
    logging.info(f"Output folder created at: {output_dir}")

    for content in content_list:
        post_id = content['post_id']
        logging.info(f"Investigating post: {post_id} ({content['post_url']}) (Type: {content['content_type']})")
        
        caption = content['content_text']
        # Pass the config_data to the mock function to get the transcript
        transcript = _transcribe_video_mock(config_data, content['media_url']) 

        # Run the RAG analysis chain
        try:
            result = chain.invoke({
                "context": legal_context,
                "transcript": transcript,
                "caption": caption
            })
            
            # --- FILE SAVING FEATURE ---
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            output_file = output_dir / f"analysis_{post_id}_{timestamp}.txt"
            
            with open(output_file, "w", encoding="utf-8") as f:
                f.write(result)
            logging.info(f"  > Analysis saved to: {output_file}")
            # --- END FILE SAVING ---

        except Exception as e:
            logging.error(f"  > Failed to analyze post {post_id}: {e}")

    logging.info(f"--- Investigation complete for: {target_username} ---")


if __name__ == "__main__":
    # This allows us to test the agent directly
    logging.basicConfig(level=logging.INFO)
    
    # We need to add a target to the command line args for testing
    if len(sys.argv) > 1:
        target_username = sys.argv[1]
        run_investigation(target_username)
    else:
        print("Please provide a target_username to investigate.")
        print("Usage: python -m nfp_agent.agents.investigator_agent [username]")