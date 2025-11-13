"""
NFPInfluencers Agent - Command Line Interface (CLI)

This is the main entrypoint for the entire application.
Run as: python -m nfp_agent.main [COMMAND]
"""
import argparse
import sys
import os

# --- THIS IS THE FIX ---
# We use relative imports (the leading dot ".") to tell main.py 
# to look for "core" and "agents" in its own directory.
from .core.database import (
    init_db, 
    add_target, 
    list_targets
)
from .core import config
# --- END FIX ---


def main():
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
    
    parser_investigate = subparsers.add_parser(
        "run_investigator", help="Scan the database for legal violations."
    )
    parser_investigate.add_argument("target_username", type=str, help="The username to investigate.")

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
            print(f"Database 'data/surveillance.db' initialized successfully.")
       
        elif args.command == "add_target":
            add_target(args.username, args.platform)
            print(f"Target '{args.username}' on '{args.platform}' added.")

        elif args.command == "list_targets":
            targets = list_targets()
            if not targets:
                print("No targets found.")
                return
            print(f"Tracking {len(targets)} targets:")
            for target in targets:
                print(f"  - [{target['id']}] {target['username']} ({target['platform']}) - Added: {target['date_added']}")
        
        # --- Placeholder Executions (Updated with relative imports) ---
        elif args.command == "run_collector":
            print("Starting Collector Daemon... (Not yet implemented)")
            # In the future: from .agents.collector_daemon import start_daemon
            # start_daemon()

        elif args.command == "run_investigator":
            print(f"Investigating '{args.target_username}'... (Not yet implemented)")
            # In the future: from .agents.investigator_agent import run_investigation
            # run_investigation(args.target_username)

        elif args.command == "run_outreach":
            print(f"Running outreach for '{args.product_name}'... (Not yet implemented)")
            # In the future: from .agents.outreach_agent import run_outreach
            # run_outreach(args.product_name)

        elif args.command == "build_case":
            print(f"Building case for '{args.target_username}'... (Not yet implemented)")
            # In the future: from .tools.case_builder import build_case
            # build_case(args.target_username)

    except Exception as e:
        print(f"An error occurred: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()