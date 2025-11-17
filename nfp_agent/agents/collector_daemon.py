import logging
import asyncio
import os
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from langchain_google_genai import ChatGoogleGenerativeAI

from ..core import database, config
from ..tools import ig_scraper
from . import investigator_agent

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
log = logging.getLogger("CollectorDaemon")

# --- Initialize LLM and Context once ---
llm = None
legal_context = None
if config.GEMINI_API_KEY:
    llm = ChatGoogleGenerativeAI(
        model="gemini-2.5-flash", 
        temperature=0.1,
        google_api_key=config.GEMINI_API_KEY
    )
    config_data = investigator_agent._load_yaml_config()
    legal_context = investigator_agent._load_rag_context(config_data)
else:
    log.error("GEMINI_API_KEY not found. Investigator job will not run.")

async def collector_job():
    """
    Job 1: Scrape all targets in the database.
    Runs the full API-based scrape for every target.
    """
    log.info("--- [COLLECTOR JOB] Starting run... ---")
    targets = database.list_targets()
    if not targets:
        log.info("[COLLECTOR JOB] No targets in database. Skipping.")
        return

    log.info(f"[COLLECTOR JOB] Found {len(targets)} targets to scrape.")
    
    # We must ensure config is valid for the scraper
    required_keys = ["IG_USERNAME", "IG_PASSWORD", "IG_APP_ID"]
    if not config.validate_config(required_keys=required_keys):
        log.error("[COLLECTOR JOB] Invalid IG config. Aborting run.")
        return

    for target in targets:
        username = target['username']
        target_id = target['id']
        log.info(f"[COLLECTOR JOB] Scraping target: {username}")
        try:
            # Call the imported scraper function
            await ig_scraper.scrape_instagram_target(
                target_id=target_id, 
                username=username,
                skip_stories=False, # We want stories
                skip_posts=True     # --- MVP SCOPE: Hardcode to True ---
            )
            log.info(f"[COLLECTOR JOB] Finished scraping {username}.")
        except Exception as e:
            log.error(f"[COLLECTOR JOB] Failed to scrape {username}: {e}", exc_info=True)
            # Continue to the next target even if one fails
            
    log.info("--- [COLLECTOR JOB] Run complete. ---")

async def investigator_job():
    """
    Job 2: Analyze all un-analyzed content.
    Finds content in the DB that doesn't have a matching analysis file.
    """
    log.info("--- [INVESTIGATOR JOB] Starting run... ---")
    if not llm or not legal_context:
        log.error("[INVESTIGATOR JOB] LLM or legal context not loaded. Skipping.")
        return

    conn = database.get_db_connection()
    try:
        # --- MVP SCOPE: Only look for story_video ---
        sql = """
        SELECT pc.*, t.username 
        FROM public_content pc
        JOIN targets t ON pc.target_id = t.id
        WHERE pc.content_type = 'story_video'
        """
        # --- END MVP SCOPE ---
        
        cursor = conn.cursor()
        cursor.execute(sql)
        content_rows = cursor.fetchall()
        
        if not content_rows:
            log.info("[INVESTIGATOR JOB] No video content found to analyze.")
            return

        log.info(f"[INVESTIGATOR JOB] Found {len(content_rows)} total video items. Checking for analysis files...")
        
        analyzed_count = 0
        for row in content_rows:
            content = dict(row)
            post_id = content['post_id']
            author_username = content['username']
            
            # Check if an analysis file *already exists*
            analysis_dir = investigator_agent.INVESTIGATION_DIR / author_username
            # Ensure analysis_dir exists before listdir
            os.makedirs(analysis_dir, exist_ok=True) 
            
            analysis_files = os.listdir(analysis_dir)
            if any(f.startswith(f"analysis_{post_id}") for f in analysis_files if os.path.isfile(os.path.join(analysis_dir, f))):
                log.info(f"  > Skipping {post_id} (already analyzed).")
                continue
                
            # --- Not analyzed, so run the analysis ---
            log.info(f"  > Analyzing new item: {post_id} from {author_username}")
            try:
                investigator_agent.analyze_content_item(content, llm, legal_context, author_username)
                analyzed_count += 1
            except Exception as e:
                log.error(f"  > Failed to analyze {post_id}: {e}", exc_info=True)

        log.info(f"--- [INVESTIGATOR JOB] Run complete. Analyzed {analyzed_count} new items. ---")

    except Exception as e:
        log.error(f"[INVESTIGATOR JOB] Database error: {e}", exc_info=True)
    finally:
        if conn:
            conn.close()

def start_daemon():
    """
    Starts the APScheduler and adds the jobs.
    """
    log.info("Starting NFPInlfuencers Surveillance Daemon...")
    scheduler = AsyncIOScheduler()
    
    # Add Job 1: Run the collector every 6 hours
    scheduler.add_job(
        collector_job,
        trigger=IntervalTrigger(hours=6),
        id="collector_job",
        replace_existing=True
    )
    
    # Add Job 2: Run the investigator every 6 hours, 5 mins after the collector
    scheduler.add_job(
        investigator_job,
        trigger=IntervalTrigger(hours=6, start_date_offset_minutes=5),
        id="investigator_job",
        replace_existing=True
    )
    
    # Run the jobs immediately on startup for testing
    log.info("Adding initial startup jobs...")
    scheduler.add_job(collector_job, id="initial_collector_run")
    # Small delay for collector to finish before investigator starts
    scheduler.add_job(investigator_job, id="initial_investigator_run", run_date_delay=30) 
    
    scheduler.start()
    log.info("Daemon started. Press Ctrl+C to exit.")
    
    # Keep the script running
    try:
        # This is the correct way to keep an asyncio event loop running
        asyncio.get_event_loop().run_forever()
    except (KeyboardInterrupt, SystemExit):
        log.info("Daemon shutting down...")
        scheduler.shutdown()