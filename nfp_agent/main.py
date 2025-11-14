"""
NFPInfluencers Agent - Command Line Interface (CLI)

This is the main entrypoint for the entire application.
Run as: python -m nfp_agent.main [COMMAND]
"""
import argparse
import sys
import os
import logging # Added logging

# --- THIS IS THE FIX ---
# We use relative imports (the leading dot ".") to tell main.py 
# to look for "core" and "agents" in its own directory.
from .core.database import (
    init_db, 
    add_target, 
    list_targets
)
from .core import config
# --- ADDED AGENT IMPORTS ---
# We now import the agent functions to be called
from .agents import investigator_agent
# --- END IMPORTS ---


def main():
    # --- Setup Logging ---
    # We set this up so all our modules log to the same standard
    logging.basicConfig(level=logging.INFO, 
                        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                        datefmt='%Y-%m-%d %H:%M:%S')

    parser = argparse.ArgumentParser(
        description="NFPInfluencers Deceptive Marketing Agent."
    )
    
    # Create subparsers for commands
    subparsers = parser.add_subparsers(dest="command", required=True)

    # --- Database Commands ---
    parser_init = subparsers.add_parser(
        "init_db", help="Initialize the surveillance database."
    )
    
    parser_add = subparsers.add_parser(
        "add_target", help="Add a new influencer to track."
    )
    parser_add.add_argument("username", type=str, help="The target's username (e.g., 'scamguru')")
    parser_add.add_argument("platform", type=str, choices=['instagram', 'tiktok', 'reddit'], help="The platform to track.")

    parser_list = subparsers.add_parser(
        "list_targets", help="List all currently tracked targets."
    )

    # --- Agent Commands (Placeholders) ---
    parser_collect = subparsers.add_parser(
        "run_collector", help="Start the 24/7 collector daemon."
    )
    
    # --- THIS IS THE UPDATE ---
    parser_investigate = subparsers.add_parser(
        "run_investigator", help="Scan the database for legal violations."
    )
    parser_investigate.add_argument("target_username", type=str, help="The username to investigate.")
    # --- END UPDATE ---

    parser_outreach = subparsers.add_parser(
        "run_outreach", help="Scan Reddit for victims and send DMs."
    )
    parser_outreach.add_argument("product_name", type=str, help="The scam product name (e.g., 'AI Profits Course')")

    parser_case = subparsers.add_parser(
        "build_case", help="Build a B2G dossier for a target."
    )
    parser_case.add_argument("target_username", type=str, help="The username to build a case against.")

    
    # Parse the arguments
    args = parser.parse_args()

    # --- Execute Commands ---
    try:
        if args.command == "init_db":
            init_db()
            logging.info(f"Database 'data/surveillance.db' initialized successfully.")
       
        elif args.command == "add_target":
            add_target(args.username, args.platform)
            logging.info(f"Target '{args.username}' on '{args.platform}' added.")

        elif args.command == "list_targets":
            targets = list_targets()
            if not targets:
                logging.info("No targets found.")
                return
            logging.info(f"Tracking {len(targets)} targets:")
            for target in targets:
                # Use logging instead of print
                logging.info(f"  - [{target['id']}] {target['username']} ({target['platform']}) - Added: {target['date_added']}")
        
        # --- Placeholder Executions (Updated with relative imports) ---
        elif args.command == "run_collector":
            logging.info("Starting Collector Daemon... (Not yet implemented)")
            # In the future: from .agents.collector_daemon import start_daemon
            # start_daemon()

        # --- THIS IS THE UPDATE ---
        elif args.command == "run_investigator":
            logging.info(f"--- Running Investigator Agent for '{args.target_username}' ---")
            investigator_agent.run_investigation(args.target_username)
            logging.info(f"--- Investigator Agent finished for '{args.target_username}' ---")
        # --- END UPDATE ---

        elif args.command == "run_outreach":
            logging.info(f"Running outreach for '{args.product_name}'... (Not yet implemented)")
            # In the future: from .agents.outreach_agent import run_outreach
            # run_outreach(args.product_name)

        elif args.command == "build_case":
            logging.info(f"Building case for '{args.target_username}'... (Not yet implemented)")
            # In the future: from .tools.case_builder import build_case
            # build_case(args.target_username)

    except Exception as e:
        logging.error(f"An error occurred: {e}", exc_info=True) # Added exc_info for better debugging
        sys.exit(1)

if __name__ == "__main__":
    main()