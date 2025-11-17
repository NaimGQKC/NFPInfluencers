import logging
import asyncio
import os
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from langchain_google_genai import ChatGoogleGenerativeAI
import datetime

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

# --- JOB 1 (Scheduled) ---
async def collector_job():
    """
    Job 1: Scrape all targets in the database.
    """
    log.info("--- [COLLECTOR JOB] Starting run... ---")
    targets = database.list_targets()
    if not targets:
        log.info("[COLLECTOR JOB] No targets in database. Skipping.")
        return

    log.info(f"[COLLECTOR JOB] Found {len(targets)} targets to scrape.")
    
    required_keys = ["IG_USERNAME", "IG_PASSWORD", "IG_APP_ID"]
    if not config.validate_config(required_keys=required_keys):
        log.error("[COLLECTOR JOB] Invalid IG config. Aborting run.")
        return

    for target in targets:
        username = target['username']
        target_id_uuid = target['id'] # This is the UUID from Supabase
        await run_collector_for_target(target_id_uuid, username)
            
    log.info("--- [COLLECTOR JOB] Run complete. ---")

# --- NEW: ON-DEMAND COLLECTOR ---
async def run_collector_for_target(target_id_uuid: str, username: str):
    """
    Runs the full collection logic for a *single* target.
    """
    log.info(f"[COLLECTOR] Scraping target: {username}")
    try:
        await ig_scraper.scrape_instagram_target(
            target_id_uuid=target_id_uuid, 
            username=username,
            skip_stories=False,
            skip_posts=True     # MVP SCOPE: Hardcode to True
        )
        log.info(f"[COLLECTOR] Finished scraping {username}.")
    except Exception as e:
        log.error(f"[COLLECTOR] Failed to scrape {username}: {e}", exc_info=True)
# --- END NEW ---

# --- JOB 2 (Scheduled) ---
async def investigator_job():
    """
    Job 2: Analyze all un-analyzed content.
    """
    log.info("--- [INVESTIGATOR JOB] Starting run... ---")
    if not llm or not legal_context:
        log.error("[INVESTIGATOR JOB] LLM or legal context not loaded. Skipping.")
        return

    try:
        # --- NEW: Use new helper function ---
        content_rows = investigator_agent._get_unanalyzed_stories()
        
        if not content_rows:
            log.info("[INVESTIGATOR JOB] No new video content found to analyze.")
            return
        
        log.info(f"[INVESTIGATOR JOB] Found {len(content_rows)} items to analyze.")
        analyzed_count = 0
        for story in content_rows:
            # --- MODIFIED: Call new modular function ---
            await run_investigator_for_story(story)
            analyzed_count += 1
            # --- END MODIFIED ---

        log.info(f"--- [INVESTIGATOR JOB] Run complete. Analyzed {analyzed_count} new items. ---")

    except Exception as e:
        log.error(f"[INVESTIGATOR JOB] Database error: {e}", exc_info=True)
    finally:
        pass # No conn.close() needed

# --- NEW: ON-DEMAND INVESTIGATOR ---
async def run_investigator_for_story(story: dict):
    """
    Runs the full investigation logic for a *single* story.
    """
    if not llm or not legal_context:
        log.error("[INVESTIGATOR] LLM or legal context not loaded. Skipping.")
        return
        
    log.info(f"  > Analyzing new item: {story['story_id']} from {story['targets']['username']}")
    try:
        # This function will now write the analysis to Supabase
        investigator_agent.analyze_content_item(story, llm, legal_context)
    except Exception as e:
        log.error(f"  > Failed to analyze {story['story_id']}: {e}", exc_info=True)
# --- END NEW ---


def start_daemon():
    """
    Starts the APScheduler and adds the jobs.
    """
    log.info("Starting NFPInlfuencers Surveillance Daemon...")
    scheduler = AsyncIOScheduler()
    
    scheduler.add_job(
        collector_job,
        trigger=IntervalTrigger(hours=6),
        id="collector_job",
        replace_existing=True
    )
    
    scheduler.add_job(
        investigator_job,
        # Run 5 minutes after the collector
        trigger=IntervalTrigger(hours=6, start_date=datetime.datetime.now() + datetime.timedelta(minutes=5)),
        id="investigator_job",
        replace_existing=True
    )
    
    log.info("Adding initial startup jobs...")
    scheduler.add_job(collector_job, id="initial_collector_run")
    # Run investigator 30 seconds after collector starts
    scheduler.add_job(investigator_job, id="initial_investigator_run", run_date=datetime.datetime.now() + datetime.timedelta(seconds=30))
    
    scheduler.start()
    log.info("Daemon started. Press Ctrl+C to exit.")
    
    try:
        asyncio.get_event_loop().run_forever()
    except (KeyboardInterrupt, SystemExit):
        log.info("Daemon shutting down...")
        scheduler.shutdown()