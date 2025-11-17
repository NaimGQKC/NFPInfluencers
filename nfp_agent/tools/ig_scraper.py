import asyncio
import logging
import os
import re
import random 
import argparse
import json
import httpx
from pathlib import Path
from datetime import datetime, timezone # Import datetime
from playwright.async_api import async_playwright
# Use absolute import to correctly reference the 'core' module outside the 'tools' package
from ..core import config, database 

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
AUTH_FILE = config.AUTH_FILE

# --- DE-SCOPED: We don't save media locally anymore ---
# MEDIA_DIR = config.BASE_DIR / "data" / "media"
# os.makedirs(MEDIA_DIR, exist_ok=True)

# --- DE-SCOPED: No longer needed as we don't filter posts ---
# AD_KEYWORDS = [
#     "#GrowingUpAnimal",
#     "@debeersgroup"
# ]


async def login_to_instagram(page): # Modified to take page
    """
    Logs into Instagram using credentials from .env
    Saves the session to auth.json to avoid logging in every time.
    """
    logging.info("Attempting Instagram login...")
    
    # --- FIX: FORCING ENGLISH LOCALE ---
    await page.goto("https://www.instagram.com/accounts/login/?hl=en")
    
    try:
        await page.wait_for_selector('input[name="username"]', timeout=10000)

        await page.fill('input[name="username"]', config.IG_USERNAME)
        await page.fill('input[name="password"]', config.IG_PASSWORD)
        await page.click('button[type="submit"]')

        await page.wait_for_url("https://www.instagram.com/**", timeout=15000)
        logging.info("Login submit successful. Handling popups...")
        try:
            await page.click('text="Not Now"', timeout=5000)
            logging.info("Clicked 'Not Now' (Save Info).")
            await page.wait_for_url("https://www.instagram.com/", timeout=10000)
        except Exception:
            logging.info("No 'Save Info' popup found, or already navigated. That's OK.")
        try:
            await page.click('text="Not Now"', timeout=5000)
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
        await page.screenshot(path="debug_login_failure.png") # Screenshot on fail
        if page and not page.is_closed():
            await page.close()
        return None
    
    # Do not close the page, the caller needs it
    return True

# --- NEW FUNCTION 1: Get User ID ---
async def get_user_id_from_username(username: str, client: httpx.AsyncClient) -> str | None:
    """
    Fetches the numerical user_id from a username using the API.
    """
    logging.info(f"  > [API] Getting user_id for {username}...")
    url = f"https://www.instagram.com/api/v1/users/web_profile_info/?username={username}"
    
    try:
        # We only need the APP_ID here, not full auth
        response = await client.get(url, headers={"X-IG-App-ID": config.IG_APP_ID})
        response.raise_for_status()
        data = response.json()
        
        user_id = data.get("data", {}).get("user", {}).get("id")
        if user_id:
            logging.info(f"  > [API] Found user_id: {user_id}")
            return user_id
        else:
            logging.warning(f"  > [API] Could not find user_id for {username} in API response.")
            return None
            
    except Exception as e:
        logging.error(f"  > [API] Error fetching user_id for {username}: {e}")
        return None

# --- NEW FUNCTION 2: The Story Scraper (Our Working MVP) ---
async def fetch_stories_via_api(target_id_uuid: str, username: str, client: httpx.AsyncClient):
    """
    Scrapes all current stories for a target using the internal v1 API.
    """
    logging.info(f"[Story Collector] Starting API-based story scrape for: {username}")
    
    user_id = await get_user_id_from_username(username, client)
    if not user_id:
        return

    story_url = f"https://www.instagram.com/api/v1/feed/user/{user_id}/story/"
    
    try:
        response = await client.get(story_url)
        response.raise_for_status()
        data = response.json()
        
        items = data.get("reel", {}).get("items", [])
        if not items:
            logging.info(f"[Story Collector] No stories found for {username}.")
            return

        logging.info(f"[Story Collector] Found {len(items)} story items. Saving...")
        saved_count = 0
        
        for item in items:
            story_id_pk = item.get("pk") # Use 'pk' as the unique ID
            if not story_id_pk:
                continue
            
            story_id = str(story_id_pk) # Ensure it's a string for DB
                
            if database.content_exists(story_id):
                logging.info(f"  > Story {story_id} already in DB. Skipping.")
                continue

            media_url = None
            media_type = "image" # Default
            
            # Get the timestamp and convert to ISO 8601 string
            taken_at_ts = item.get("taken_at", int(datetime.now(timezone.utc).timestamp()))
            timestamp_utc = datetime.fromtimestamp(taken_at_ts, tz=timezone.utc).isoformat()
            
            if item.get("video_versions"):
                media_url = item["video_versions"][0]["url"]
                media_type = "video"
            elif item.get("image_versions2"):
                media_url = item["image_versions2"]["candidates"][0]["url"]
                media_type = "image"
            
            if not media_url:
                logging.warning(f"  > No media_url found for story {story_id}. Skipping.")
                continue
                
            try:
                # --- MODIFICATION: We now call save_story ---
                # We save the public URL, not the local file
                database.save_story(
                    target_id_uuid=target_id_uuid,
                    story_id=story_id,
                    timestamp=timestamp_utc,
                    media_type=media_type,
                    media_url=media_url # Save the direct URL
                )
                logging.info(f"  > [API] Saved story {media_type}: {story_id} to Supabase.")
                saved_count += 1
                
            except Exception as e:
                logging.error(f"  > [API] Failed to save story asset {story_id}: {e}")

        logging.info(f"[Story Collector] Saved {saved_count} new story items to DB.")

    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            logging.info(f"[Story Collector] No stories found for {username} (404).")
        else:
            logging.error(f"[Story Collector] Error fetching story feed for {username}: {e}")
    except Exception as e:
        logging.error(f"[Story Collector] Error processing story feed for {username}: {e}")


# --- DE-SCOPED: fetch_post_data_via_graphql() has been commented out ---
# async def fetch_post_data_via_graphql(shortcode: str, client: httpx.AsyncClient) -> dict:
#     """
#     Fetches post/reel data using the internal GraphQL API.
#     Based on ahmedrangel/instagram-media-scraper.
#     """
#     logging.info(f"  > [GraphQL] Fetching post data for {shortcode}...")
    
#     if not config.IG_APP_ID:
#         logging.error("  > [GraphQL] FATAL: IG_APP_ID not configured in .env.")
#         return {}

#     graphql_url = "https://www.instagram.com/api/graphql"
#     params = {
#         "variables": json.dumps({"shortcode": shortcode}),
#         "doc_id": "10015901848480474", # Static doc_id from scraper.js
#         "lsd": "AVqbxe3J_YA",
#     }
    
#     # --- THIS IS THE FIX ---
#     # We start with the client's existing headers (which has the Cookie)
#     # and then add the new ones needed for this specific request.
#     merged_headers = dict(client.headers)
#     merged_headers.update({
#         "Content-Type": "application/x-www-form-urlencoded",
#         "X-FB-LSD": "AVqbxe3J_YA",
#         "X-ASBD-ID": "129477",
#         "Sec-Fetch-Site": "same-origin"
#     })
#     # --- END THE FIX ---

#     try:
#         # Use the new 'merged_headers'
#         response = await client.post(graphql_url, data=params, headers=merged_headers)
#         response.raise_for_status()
        
#         data = response.json()
#         items = data.get("data", {}).get("xdt_shortcode_media")

#         if not items:
#             logging.warning(f"  > [GraphQL] No items found in response for {shortcode}.")
#             return {}

#         caption_edge = items.get("edge_media_to_caption", {}).get("edges", [])
#         return {
#             "video_url": items.get("video_url"),
#             "caption": caption_edge[0]["node"]["text"] if caption_edge else "",
#             "product_type": items.get("product_type"),
#         }

#     except Exception as e:
#         # Now, this error will be more specific if it's not a JSON error
#         logging.error(f"  > [GraphQL] Error fetching {shortcode}: {e}")
#         return {}
# --- END DE-SCOPED ---


# --- REWRITTEN MAIN FUNCTION (V2.2 - Stories-Only) ---
async def scrape_instagram_target(target_id_uuid: str, username: str, skip_stories=False, skip_posts=True):
    """
    SCRAPER MODE: "HYBRID API" (V2.2 - Stories-Only)
    Uses Playwright ONLY to log in, then scrapes stories via
    direct API calls using the authenticated session.
    """
    logging.info(f"[Hybrid Scraper] Starting scrape for: {username} (ID: {target_id_uuid})")
    
    # skip_posts is now ignored, we will always skip them.
    if skip_stories:
        logging.info("[CLI] Skipping story scraping. Nothing to do.")
        return

    async with async_playwright() as p:
        
        # --- 1. LOGIN & SESSION ---
        logging.info("Launching browser to get auth session...")
        browser = await p.chromium.launch(
            headless=False, # Must be headed for first login
            slow_mo=50 
        )
        
        # We need a page to check login status
        page = await browser.new_page()
        
        if not os.path.exists(AUTH_FILE):
            if not await login_to_instagram(page):
                await browser.close()
                return False 
        
        # We create the context *after* login is confirmed
        await page.close() # Close the login tab
        context = await browser.new_context(storage_state=AUTH_FILE)
        page = await context.new_page()

        logging.info("Warming up session by visiting main feed...")
        try:
            await page.goto("https://www.instagram.com/")
            await page.wait_for_selector('a[href="/explore/"]', timeout=10000)
            logging.info("Main feed loaded. Session is warm.")
        except Exception as e:
            logging.warning(f"Could not warm up session: {e}. Deleting auth.json.")
            if os.path.exists(AUTH_FILE):
                os.remove(AUTH_FILE)
            await context.close()
            await browser.close()
            return False

        # --- 2. CREATE THE API CLIENT (using live cookies) ---
        logging.info("Extracting cookies from browser session for API calls...")
        cookies = await context.cookies()
        cookie_str = "; ".join([f"{c['name']}={c['value']}" for c in cookies])
        
        if not cookie_str:
            logging.error("Failed to extract cookies. Can't make API calls.")
            await context.close()
            await browser.close()
            return
            
        api_headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
            "X-IG-App-ID": config.IG_APP_ID,
            "Cookie": cookie_str
        }
        
        # We can now close the browser, we *only* need the API client
        await context.close()
        await browser.close()
        logging.info("Browser closed. Proceeding with API-only scraping.")

        # --- 3. START SCRAPING (using the API client) ---
        async with httpx.AsyncClient(headers=api_headers, follow_redirects=True, timeout=30.0) as client:

            # --- 4. START STORY SCRAPING (API METHOD) ---
            if not skip_stories:
                await fetch_stories_via_api(target_id_uuid, username, client)
            else:
                logging.info("[CLI] Skipping story scraping.")

            # --- 5. POST SCRAPING IS NOW DE-SCOPED ---
            logging.info("[MVP SCOPE] Post scraping is de-scoped. Skipping.")
            # if not skip_posts:
            #   ... (all post scraping code is commented out) ...
            # else:
            #   logging.info("[CLI] Skipping post scraping.")

        logging.info(f"Hybrid API Scrape complete for {username}.")


async def main():
    parser = argparse.ArgumentParser(description="NFPInfluencers Instagram Scraper")
    parser.add_argument(
        "--no-stories",
        action="store_true",
        help="Do not scrape 24-hour stories."
    )
    
    # --- DE-SCOPED: Commented out the --no-posts argument ---
    # parser.add_argument(
    #     "--no-posts",
    #     action="store_true",
    #     help="Do not scrape posts/reels."
    # )
    
    parser.add_argument(
        "target_username",
        type=str,
        nargs="?", # Makes it optional
        default="natgeo", # Default to natgeo for testing
        help="The @username of the target to scrape."
    )
    args = parser.parse_args()

    logging.info("--- [DIRECT TEST MODE] ---")
    
    # --- MODIFIED: Added Supabase keys to validation ---
    required_keys = ["IG_USERNAME", "IG_PASSWORD", "IG_APP_ID", "SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY"]
    if not config.validate_config(required_keys=required_keys):
        logging.error(f"CRITICAL: Required keys not in .env. Exiting.")
        exit(1)

    target_username = args.target_username
    logging.info(f"Testing Collector: Scraping target '{target_username}'...")
    
    # --- MODIFIED: Use new add_target which returns the target object ---
    target = database.get_target_by_name(target_username)
    if not target:
        logging.warning(f"Test target '{target_username}' not in database. Adding it for this test.")
        # Use new add_target function
        target = database.add_target(target_username, "instagram")
        
    if not target:
        logging.error("Failed to add or get target. Exiting test.")
        return

    await scrape_instagram_target(
        target_id_uuid=target['id'], # Pass the UUID
        username=target['username'],
        skip_stories=args.no_stories,
        skip_posts=True # --- We now hardcode this to True ---
    )
    
    logging.info("Collector test done. Check Supabase.")


if __name__ == "__main__":
    asyncio.run(main())