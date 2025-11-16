"""
Video URL Tester
This script checks if media_urls stored in the database are still 
accessible using a logged-in Playwright session.

Run this AFTER you have run the main ig_scraper.py at least once.
This test requires:
1. A populated `data/surveillance.db` file.
2. An `auth.json` file (created by a successful scraper login).

Usage:
python -m nfp_agent.tools.video_url_tester
"""
import asyncio
import logging
import os
import sys
from playwright.async_api import async_playwright
# Use relative imports to access core modules
from ..core import config, database

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

async def run_test():
    """
    Grabs one video URL from the DB and tries to open it.
    """
    logging.info("--- Starting Video URL Test ---")

    # --- 1. Check for Auth File ---
    if not os.path.exists(config.AUTH_FILE):
        logging.error(f"CRITICAL: auth.json not found at {config.AUTH_FILE}")
        logging.error("Please run the main ig_scraper.py first to log in.")
        return

    # --- 2. Get a Video URL from the Database ---
    video_url_to_test = None
    try:
        conn = database.get_db_connection()
        cursor = conn.cursor()
        
        # --- FIX: Query now looks for any media_url that starts with the Instagram CDN link ---
        query = """
        SELECT media_url FROM public_content 
        WHERE 
            media_url IS NOT NULL 
            AND media_url LIKE 'https://scontent%' -- Instagram CDN signature
        ORDER BY scraped_at DESC 
        LIMIT 1
        """
        
        cursor.execute(query)
        row = cursor.fetchone()
        conn.close()
        
        if row and row['media_url']:
            video_url_to_test = row['media_url']
            logging.info(f"Found URL to test: {video_url_to_test}")
        else:
            logging.error("No likely video content URLs found in the database using the CDN signature.")
            logging.error("Please ensure the scraper has run successfully recently.")
            return

    except Exception as e:
        logging.error(f"Error querying database: {e}")
        return

    # --- 3. Run the Playwright Test ---
    async with async_playwright() as p:
        logging.info("Launching browser (headed)...")
        browser = await p.chromium.launch(
            headless=False,  # Run headed so you can see
            slow_mo=50
        )
        
        # Load the saved login session
        context = await browser.new_context(
            storage_state=config.AUTH_FILE,
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        
        try:
            logging.info(f"Navigating directly to media URL...")
            
            # Go to the URL
            await page.goto(video_url_to_test)
            
            logging.info("Waiting 5 seconds for video to load...")
            await page.wait_for_timeout(5000)
            
            # Take the screenshot
            screenshot_path = "video_test_result.png"
            await page.screenshot(path=screenshot_path)
            
            logging.info("--- TEST SUCCESSFUL ---")
            logging.info(f"Screenshot saved to: {os.path.abspath(screenshot_path)}")
            logging.info("Check the screenshot to see if the video loaded.")

        except Exception as e:
            logging.error(f"--- TEST FAILED ---")
            logging.error(f"Failed to navigate to URL: {e}")
            await page.screenshot(path="video_test_FAIL.png")
            logging.info("Saved failure screenshot to video_test_FAIL.png")
        
        finally:
            await context.close()
            await browser.close()
            logging.info("Browser closed.")

def main():
    try:
        asyncio.run(run_test())
    except KeyboardInterrupt:
        logging.info("Test interrupted by user.")

if __name__ == "__main__":
    # This allows us to run this file as a module:
    # python -m nfp_agent.tools.video_url_tester
    main()