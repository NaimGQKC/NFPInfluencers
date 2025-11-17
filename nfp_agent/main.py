import argparse
import sys
import os
import logging
# --- NEW: Import asyncio for the new async command ---
import asyncio 

from .core.database import (
    init_db, 
    add_target, 
    list_targets,
    get_db_connection, # NEW: For investigator_job
    get_target_by_name  # NEW: For run_single_job
)
from .core import config
from .agents import investigator_agent
# --- NEW DAEMON IMPORT ---
from .agents import collector_daemon

# --- NEW: Async function to run a single job ---
async def run_single_job(username: str):
    """
    Called by the 'run_now' command to execute the full
    scrape-and-investigate flow for one target.
    """
    log = logging.getLogger("RunNow")
    log.info(f"--- [RUN NOW] Starting instant job for: {username} ---")
    
    # 1. Validate Config
    required_keys = ["IG_USERNAME", "IG_PASSWORD", "IG_APP_ID", "SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY", "GEMINI_API_KEY"]
    if not config.validate_config(required_keys=required_keys):
        log.error("[RUN NOW] Invalid config. Aborting.")
        return

    # 2. Get Target from DB
    target = database.get_target_by_name(username)
    if not target:
        log.error(f"[RUN NOW] Target '{username}' not found in DB. Did frontend save it?")
        return
        
    target_id_uuid = target['id']
    
    # 3. Run Collector
    await collector_daemon.run_collector_for_target(target_id_uuid, username)
    
    # 4. Run Investigator
    log.info(f"[RUN NOW] Collection for {username} complete. Starting investigation...")
    
    # Get *only* the new stories for this target
    db = database.get_db_connection()
    response = db.table('stories').select('*, targets!inner(username)') \
        .eq('media_type', 'video') \
        .is_('full_analysis', 'null') \
        .eq('targets.username', username) \
        .execute()
        
    stories_to_analyze = response.data
    log.info(f"[RUN NOW] Found {len(stories_to_analyze)} new items to investigate.")
    
    for story in stories_to_analyze:
        await collector_daemon.run_investigator_for_story(story)
        
    log.info(f"--- [RUN NOW] Job for {username} complete. ---")
# --- END NEW ---


def main():
    logging.basicConfig(level=logging.INFO, 
                        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                        datefmt='%Y-%m-%d %H:%M:%S')

    parser = argparse.ArgumentParser(
        description="NFPInfluencers Deceptive Marketing Agent."
    )
    
    subparsers = parser.add_subparsers(dest="command", required=True)

    # --- Database Commands ---
    parser_init = subparsers.add_parser(
        "init_db", help="Initialize the Supabase database connection."
    )
    
    parser_add = subparsers.add_parser(
        "add_target", help="Add a new influencer to track."
    )
    parser_add.add_argument("username", type=str, help="The target's username (e.g., 'scamguru')")
    parser_add.add_argument("platform", type=str, choices=['instagram'], default='instagram', nargs='?', help="The platform to track (default: instagram).")

    parser_list = subparsers.add_parser(
        "list_targets", help="List all currently tracked targets."
    )

    # --- Agent Commands ---
    
    # --- NEW DAEMON COMMAND ---
    parser_daemon = subparsers.add_parser(
        "run_daemon", help="Start the 24/7 surveillance daemon."
    )
    # --- END NEW COMMAND ---

    # --- NEW: 'run_now' command for the frontend demo ---
    parser_run_now = subparsers.add_parser(
        "run_now", help="Run a single scrape/investigation for one target."
    )
    parser_run_now.add_argument("target_username", type=str, help="The username to run.")
    # --- END NEW ---
    
    # --- DE-SCOPED: Removed run_collector ---
    
    parser_investigate = subparsers.add_parser(
        "run_investigator", help="Run a manual investigation on ALL of a target's content."
    )
    parser_investigate.add_argument("target_username", type=str, help="The username to investigate.")

    # --- DE-SCOPED: Removed run_outreach ---

    parser_case = subparsers.add_parser(
        "build_case", help="Build a B2G dossier for a target. (Not Implemented)"
    )
    parser_case.add_argument("target_username", type=str, help="The username to build a case against.")

    
    args = parser.parse_args()

    try:
        if args.command == "init_db":
            init_db()
            # logging.info(f"Database 'data/surveillance.db' initialized successfully.") # Old message
       
        elif args.command == "add_target":
            add_target(args.username, args.platform)
            # logging.info(f"Target '{args.username}' on '{args.platform}' added.") # DB function now logs this

        elif args.command == "list_targets":
            targets = list_targets()
            if not targets:
                logging.info("No targets found.")
                return
            logging.info(f"Tracking {len(targets)} targets:")
            for target in targets:
                # Updated to match Supabase schema
                logging.info(f"  - [{target['id']}] {target['username']} (Dossier: {target['dossier_id']}) - Added: {target['created_at']}")
        
        # --- NEW DAEMON EXECUTION ---
        elif args.command == "run_daemon":
            collector_daemon.start_daemon()
        # --- END NEW EXECUTION ---

        # --- NEW: Handle 'run_now' command ---
        elif args.command == "run_now":
            # We must use asyncio.run for this async command
            try:
                asyncio.run(run_single_job(args.target_username))
            except Exception as e:
                logging.error(f"Error during 'run_now': {e}", exc_info=True)
        # --- END NEW ---

        elif args.command == "run_investigator":
            logging.info(f"--- Running Investigator Agent for '{args.target_username}' ---")
            investigator_agent.run_investigation_for_target(args.target_username)
            logging.info(f"--- Investigator Agent finished for '{args.target_username}' ---")

        elif args.command == "build_case":
            logging.info(f"Building case for '{args.target_username}'... (Not Implemented)")

    except Exception as e:
        logging.error(f"An error occurred: {e}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    main()