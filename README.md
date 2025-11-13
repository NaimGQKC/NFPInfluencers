NFPInfluencers: The Deceptive Marketing Agent

Our Mission: To build an open-source "sword" that protects consumers by creating ironclad, evidence-based cases against deceptive marketers and "finfluencers."

We are a community-led non-profit project building a tool to fight back against the wave of "get-rich-quick" schemes, fake courses, and undisclosed crypto promotions that target vulnerable people online.

This project was started after a founder's family member was targeted by one of these scams. We are not a "shield" (we can't stop the scam in real-time); we are a "sword". We build the tools to help regulators, journalists, and victims create un-ignorable, evidence-based dossiers to get these bad actors de-platformed, fined, or prosecuted.

How it Works: The "Pincer" Strategy

Our agent uses a "double approach" to build a case:

Top-Down (The Collector Agent): A 24/7 surveillance agent that monitors target influencers (on IG, TikTok) and creates a permanent, private archive of their content—especially the 24-hour stories that are used to avoid accountability.

Bottom-Up (The Outreach Agent): A tool to find victims on review sites (like Reddit) and invite them to an anonymous "digital drop box" to submit their private evidence (receipts, DMs, emails).

The Result (The Investigator Agent): The agent combines the public claims (from the Collector) with the private proof (from victims) to generate a "B2G Dossier" ready for the Ontario Securities Commission (OSC) and the Competition Bureau of Canada.

⭐ How You Can Help

This is a non-profit, open-source, community-led project. We need all the help we can get.

For Coders & Researchers

You are the lifeblood of this project. We have a clear roadmap and need your help.

See our CONTRIBUTING.md file for the full tech stack (Python, LangChain, Playwright) and the project roadmap.

Check out the "Issues" tab to find a task to work on.

For Funders & Supporters

We are 100% community-funded. Our code is free, but our infrastructure (proxies, servers) is not. Your donation directly pays for the tools we use to hunt for scammers.

Sponsor this Project on GitHub

(We will add more links here as we set them up)

Our Roadmap (V1)

[x] Phase 1: Core Infrastructure

[x] nfp_agent/core/database.py: Set up the SQLite database.

[x] nfp_agent/main.py: Set up the main CLI.

[x] nfp_agent/core/config.py: Load secrets.

[x] All community & documentation files.

[ ] Phase 2: The Collector Agent (The Camera)

[ ] tools/ig_scraper.py / tools/reddit_scraper.py: Build the scrapers.

[ ] agents/collector_daemon.py: Build the 24/7 scheduler (APScheduler).

[ ] Phase 3: The Investigator & Outreach Agents (The Detective)

[ ] agents/investigator_agent.py: Build the LLM-powered agent (LangChain + Gemini).

[ ] agents/outreach_agent.py: Build the agent to DM victims on Reddit.

[ ] tools/case_builder.py: Build the tool that creates the final .zip dossier.

Legal Disclaimer

This tool is for evidence-gathering and research purposes. We are not a law firm and do not provide legal advice. All dossiers are intended to be submitted to official regulatory bodies (like the OSC and Competition Bureau) for their own investigation.