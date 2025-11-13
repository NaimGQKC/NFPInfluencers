import asyncio
import logging
import os
import re
import random 
from playwright.async_api import async_playwright
from nfp_agent.core import config, database

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
AUTH_FILE = config.AUTH_FILE

async def login_to_instagram(browser):
# ... (login_to_instagram function unchanged) ...
    """
    Logs into Instagram using credentials from .env
    Saves the session to auth.json to avoid logging in every time.
    """
    logging.info("Attempting Instagram login...")
    page = await browser.new_page()
    await page.goto("https://www.instagram.com/accounts/login/")
    
    await page.wait_for_selector('input[name="username"]', timeout=10000)

    await page.fill('input[name="username"]', config.IG_USERNAME)
    await page.fill('input[name="password"]', config.IG_PASSWORD)
    await page.click('button[type="submit"]')

    try:
        await page.wait_for_url("https://www.instagram.com/**", timeout=15000)
        logging.info("Login submit successful. Handling popups...")

        # 1. Handle "Save Info?" or "One-Tap" page
        try:
            await page.click('text="Not Now"', timeout=5000) # 5 sec timeout
            logging.info("Clicked 'Not Now' (Save Info).")
            await page.wait_for_url("https://www.instagram.com/", timeout=10000)
        except Exception:
            logging.info("No 'Save Info' popup found, or already navigated. That's OK.")

        # 2. Handle "Turn on Notifications?" popup
        try:
            await page.click('text="Not Now"', timeout=5000) # 5 sec timeout
            logging.info("Clicked 'Not Now' (Notifications).")
        except Exception:
            logging.info("No 'Notifications' popup found. That's OK.")

        if "instagram.com" in page.url:
            logging.info("Login successful. Saving auth state...")
            await page.context.storage_state(path=AUTH_FILE)
            logging.info(f"Auth state saved to {AUTH_FILE}")
        else:
            logging.error("Landed on an unexpected page. Login failed.")
            await page.close()
            return None

    except Exception as e:
        logging.error(f"Login flow failed: {e}")
        await page.close()
        return None
    
    await page.close()
    return True


async def scrape_instagram_target(target_id: int, username: str):
    """
    SCRAPER MODE 1: COLLECTOR (V12 - "The Debugger")
    Takes a screenshot inside the loop to debug selectors.
    """
    logging.info(f"[Collector] Starting Instagram scrape for: {username} (ID: {target_id})")
    
    async with async_playwright() as p:
        
        logging.info("Launching in HEADED mode (visible browser) for debugging.")
        browser = await p.chromium.launch(headless=False, args=["--disable-gpu"])
        
        if not os.path.exists(AUTH_FILE):
            if not await login_to_instagram(browser):
                await browser.close()
                return False 
        
        context = await browser.new_context(
            storage_state=AUTH_FILE,
            viewport={'width': 1280, 'height': 800}
        )
        page = await context.new_page()

        logging.info("Warming up session by visiting main feed...")
        try:
            await page.goto("https://www.instagram.com/")
            await page.wait_for_selector('a[href="/explore/"]', timeout=10000)
            logging.info("Main feed loaded. Session is warm.")
        except Exception as e:
            logging.warning(f"Could not warm up session: {e}. Deleting auth.json to force re-login.")
            if os.path.exists(AUTH_FILE):
                os.remove(AUTH_FILE)
            await context.close()
            await browser.close()
            return False

        # --- Scraping ---
        try:
            profile_url = f"https://www.instagram.com/{username}/"
            await page.goto(profile_url)
            
            # --- 1. DISMISS POPUPS ---
            try:
                logging.info("Waiting for any 'Messages' or 'Try' popups...")
                dismiss_button = page.locator('svg[aria-label="Dismiss"]').first
                await dismiss_button.wait_for(state="visible", timeout=5000)
                await dismiss_button.click()
                logging.info("Dismissed 'Messages' popup.")
            except Exception:
                logging.info("No 'Messages' popup found. Continuing...")
            
            logging.info(f"Waiting for profile page to load...")
            await page.wait_for_timeout(2000) 
            
            logging.info(f"Simulating human scrolling to trigger JS...")
            await page.evaluate("window.scrollBy(0, 1000)") 
            
            await page.wait_for_timeout(2000) # Wait 2s for posts to load after scroll

            # --- 2. "DUMB" CLICK ---
            CLICK_X = 400 
            CLICK_Y = 500 
            
            logging.info(f"Performing 'human' mouse click at ({CLICK_X}, {CLICK_Y})...")
            await page.mouse.click(CLICK_X, CLICK_Y)
            
            logging.info("Clicked first post. Waiting for modal...")
            
            modal_selector = 'div[role="dialog"]'
            await page.wait_for_selector(modal_selector, timeout=10000)
            logging.info("Modal is open. Starting scrape loop...")

            saved_count = 0
            for i in range(12): # Scrape 12 posts
                # --- 2. ADD RANDOM DELAY ---
                # Wait a random time between 2.5 and 5 seconds to act human
                human_wait_ms = random.randint(2500, 5000)
                logging.info(f"Scraping post {i+1}/12... (waiting {human_wait_ms}ms)")
                await page.wait_for_timeout(human_wait_ms) 
                
                # --- THIS IS THE FIX: TAKE A SCREENSHOT ---
                screenshot_path = f"debug_post_{i+1}.png"
                await page.screenshot(path=screenshot_path)
                logging.info(f"Saved screenshot to {screenshot_path}")
                # --- END FIX ---

                current_url = page.url
                # --- RESTORING MISSING LINE ---
                post_id_match = re.search(r"/(p|reel)/([^/]+)", current_url)
                # --- END RESTORATION ---

                if not post_id_match:
                    logging.warning("Could not find post ID in URL. Skipping.")
                    continue
                
                post_id = post_id_match.group(2)
                content_type = 'post' if post_id_match.group(1) == 'p' else 'reel'
                
                # --- POST CHECK COMMENTED OUT FOR DEBUGGING ---
                # if database.content_exists(post_id):
                #     logging.info(f"Post {post_id} already in DB. Ending scrape task.")
                #     break 

                content_text = "No caption found."
                try:
                    # Based on image_d51d07.jpg, the caption is a span
                    caption_element = page.locator('div[role="dialog"] span._aade').first
                    content_text = await caption_element.text_content(timeout=1000)
                except Exception:
                    try:
                        # Fallback for other post types
                        caption_element = page.locator('div[role="dialog"] h1').first
                        content_text = await caption_element.text_content(timeout=1000)
                    except Exception:
                        pass # No caption found

                media_url = None
                try:
                    # Find the main media (video or image) inside the dialog
                    media_element = page.locator(
                        'div[role="dialog"] div[role="presentation"] video,' +
                        'div[role="dialog"] div[role="presentation"] img[style*="object-fit"]'
                    ).first
                    media_url = await media_element.get_attribute("src", timeout=1000)
                except Exception:
                    logging.warning(f"Could not extract media URL for {post_id}")
                
                # --- 3. ADD GUARDRAIL ---
                # If we failed to get a media URL, it's likely an error page.
                # Do not save it, and log a specific warning.
                if not media_url:
                    logging.warning(f"No media_url found for {post_id}. This might be a 'media error' page. Skipping save.")
                else:
                    database.save_content(
                        target_id=target_id,
                        platform='instagram',
                        post_id=post_id,
                        content_type=content_type,
                        content_text=content_text.strip(),
                        media_url=media_url,
                        post_url=current_url,
                        author_username=username
                    )
                    logging.info(f"[Collector] Saved new {content_type}: {post_id} for {username}")
                    saved_count += 1

                try:
                    # Add a small random wait before clicking next
                    await page.wait_for_timeout(random.randint(500, 1500))
                    
                    # --- FIX: Use keyboard navigation instead of selector click ---
                    logging.info("Attempting to move to the next post via Right Arrow key...")
                    await page.keyboard.press('ArrowRight')
                    
                except Exception:
                    logging.info("No 'Next' button found (or keyboard failed). Assuming end of posts.")
                    break 
            
            logging.info(f"Scrape complete for {username}. Found {saved_count} new posts.")

        except Exception as e:
            logging.error(f"[Collector] Error scraping {username}: {e}")
            screenshot_path = "debug_screenshot.png"
            await page.screenshot(path=screenshot_path)
            logging.error(f"Saved a screenshot of the failure to {screenshot_path}")
            
            if "page.wait_for_selector" in str(e):
                logging.error(f"Failed to load profile for {username}. Check debug_screenshot.png.")
            if "storage_state" in str(e) or "login" in str(e):
                logging.warning("Auth token may be expired or invalid. Deleting auth.json.")
                if os.path.exists(AUTH_FILE):
                    os.remove(AUTH_FILE)
        finally:
            await context.close()
            await browser.close()

# This block allows us to run and test this file directly
async def main():
    logging.info("--- [DIRECT TEST MODE] ---")
    
    if not config.validate_config(required_keys=["IG_USERNAME", "IG_PASSWORD"]):
        logging.error("CRITICAL: IG_USERNAME and IG_PASSWORD not in .env. Exiting.")
        exit(1)

    logging.info("Testing Collector: Scraping target 'natgeo'...")
    target = database.get_target_by_name("natgeo")
    if target:
        await scrape_instagram_target(target['id'], target['username'])
        logging.info("Collector test done. Check data/surveillance.db.")
    else:
        logging.warning("Test target 'natgeo' not in database. Skipping Collector test.")
        logging.warning("Please run this in another terminal:")
        logging.warning("python -m nfp_agent.main add_target \"natgeo\" \"instagram\"")

if __name__ == "__main__":
    asyncio.run(main())