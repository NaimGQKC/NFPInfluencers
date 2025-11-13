How to Contribute to NFPInfluencers

First off, thank you for considering contributing. You are joining a mission to use technology to fight exploitation, and your help is what makes this project possible.

We are building a community of developers, researchers, and investigators, and we welcome all skill levels.

Guiding Principles

We are the "Sword," not the "Shield." Our tools are for building legal cases after the fact, not for real-time prevention.

Privacy & Anonymity are Paramount. Our B2G partners (regulators) and victim sources must be protected.

Evidence Must Be Verifiable. All data must be logged with timestamps and source URLs.

The V1 Tech Stack

The V1 Agent is a Python-based CLI tool.

Core: Python 3.10+

Agent Framework: LangChain (using Gemini 1.5 Pro)

Web Scraping: Playwright (for IG/TikTok), PRAW (for Reddit)

Scheduling: APScheduler (for the 24/7 Collector)

Database: SQLite (for simple, local evidence-logging)

Environment: python-dotenv

How to Get Started

Fork the Repository: Create your own copy of the project to work on.

Set Up Your Environment:

# Clone your fork
git clone [https://github.com/YOUR-USERNAME/NFPInfluencers.git](https://github.com/YOUR-USERNAME/NFPInfluencers.git)
cd NFPInfluencers

# Create and activate a virtual environment
python -m venv venv
source venv/bin/activate  # or .\venv\Scripts\Activate on Windows

# Install dependencies
pip install -r requirements.txt

# Install browser engines for Playwright
python -m playwright install

# Set up your local .env file
cp .env.example .env
# Now, edit .env and add your private API keys


Find an Issue to Work On:

Go to the "Issues" tab in our GitHub repo.

Look for issues tagged good first issue. These are perfect for new contributors.

If you have a new idea, please create a new "Feature Request" issue to discuss it before you start coding.

Submit Your Code (Pull Request):

Create a new branch for your feature: git checkout -b feature/my-new-scraper

Write your code and add tests for it.

Commit your changes: git commit -m "feat: Add new scraper for [platform]"

Push to your branch: git push origin feature/my-new-scraper

Open a Pull Request (PR) from your fork to our main branch.

Fill out the PR template so we understand what you changed.

Our V1 Roadmap

We are currently focused on building the core V1 agent. Help is needed on all of these:

[ ] Collector Tools (tools/collector.py): We need robust, proxy-enabled scrapers for:

[ ] Instagram (Posts & Stories)

[ ] TikTok (Posts)

[ ] Reddit (via PRAW)

[ ] Agent Logic (agent/):

[ ] collector_daemon.py: Logic for the APScheduler to run the scrapers 24/7.

[ ] investigator.py: The LangChain prompts to find legal violations.

[ ] outreach_agent.py: The PRAW logic to find victims and send DMs.

Thank you for building this with us.