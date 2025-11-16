import asyncio
import logging
import os
import re
import random 
import argparse # For CLI options
import json
import httpx
from playwright.async_api import async_playwright
# Use absolute import to correctly reference the 'core' module outside the 'tools' package
from ..core import config, database 

MEDIA_DIR = config.BASE_DIR / "data" / "media"
os.makedirs(MEDIA_DIR, exist_ok=True)

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
AUTH_FILE = config.AUTH_FILE

# --- FIXED TEST TARGET (from user) ---
AD_KEYWORDS = [
    "#GrowingUpAnimal",
    "@debeersgroup" # NEW: Based on user finding (case-insensitive check will handle this)
]
# --- END FIXED TEST TARGET ---


async def login_to_instagram(browser):
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
        await page.close()
        return None
    
    await page.close()
    return True


async def scrape_instagram_stories(page, target_id: int, username: str):
    """
    SCRAPER MODE 6: "PASSIVE COLLECTION" (V1.7 - Anti-Ban)
    This clicks the story ring and then waits passively, letting stories
    auto-play to trigger network requests for full-res media.
    """
    logging.info(f"[Story Collector] Starting PASSIVE network scrape for: {username}")
    
    # Use a dict to store structured data {post_id: {path: '...', type: '...'}}
    intercepted_media = {} 

    async def story_network_handler(request):
        """Listen for story media files and save them to disk."""
        
        # --- THIS IS THE FIX ---
        # If we aren't in the story modal, ignore all requests.
        if "/stories/" not in page.url:
            return
        # --- END THE FIX ---

        url = request.url
        # We are now more specific: we want video, or "image" that is NOT a preview
        if "scontent" in url and ("PREVIEW" not in url.upper()):
            if ('.mp4' in url) or ('.jpg' in url and "resize" not in url):
                
                # Create a unique ID based on the media URL hash
                post_id = f"story_{abs(hash(url))}"

                if post_id in intercepted_media:
                    return # Already processed

                try:
                    response = await request.response()
                    if response:
                        buffer = await response.body()
                        
                        content_type = 'story_video' if '.mp4' in url else 'story_image'
                        extension = '.mp4' if content_type == 'story_video' else '.jpg'
                        local_path = MEDIA_DIR / f"{post_id}{extension}"
                        
                        with open(local_path, "wb") as f:
                            f.write(buffer)
                        
                        logging.info(f"  > [STORY NETWORK] Saved asset ({content_type}): {local_path}")
                        
                        intercepted_media[post_id] = {
                            'path': str(local_path), 
                            'type': content_type
                        }
                        
                except Exception as e:
                    logging.warning(f"  > [STORY NETWORK] Failed to save asset bytes for {url}: {e}")

    page.on("request", story_network_handler)

    try:
        # 1. Click the story ring to open it
        profile_pic_selector = f'div[role="button"]:has(canvas)'
        logging.info(f"Looking for story button with selector: {profile_pic_selector}")
        
        await page.wait_for_selector(profile_pic_selector, timeout=5000)
        await page.locator(profile_pic_selector).first.click()
        logging.info("Clicked profile picture to open stories.")
        
        # 2. Wait for story modal
        await page.wait_for_url("https://www.instagram.com/stories/**", timeout=10000)
        logging.info("Story modal is open. Starting passive collection...")

        # 3. --- THIS IS THE NEW LOGIC ---
        # Instead of "burst scraping", we wait passively for 60 seconds.
        # The stories will auto-play, triggering the network handler.
        # This is more human-like and allows videos to load.
        passive_wait_ms = 6000
        logging.info(f"Waiting {passive_wait_ms / 1000} seconds for stories to auto-play...")
        await page.wait_for_timeout(passive_wait_ms) 
        # --- END NEW LOGIC ---
        
        logging.info(f"Passive collection complete. Found {len(intercepted_media)} unique media items.")

    except Exception as e:
        if "timeout" in str(e).lower():
            logging.info(f"[Story Collector] No stories found for {username} (or selector failed).")
        else:
            logging.error(f"[Story Collector] Error scraping stories: {e}")
            await page.screenshot(path="debug_story_failure.png")
    
    finally:
        # 4. CRITICAL: Remove the listener
        page.remove_listener("request", story_network_handler)

        # 5. Save all unique media found (same as before)
        saved_count = 0
        for post_id, media_data in intercepted_media.items():
            if not database.content_exists(post_id):
                local_path = media_data['path']
                content_type = media_data['type']
                
                database.save_content(
                    target_id=target_id,
                    platform='instagram',
                    post_id=post_id,
                    content_type=content_type,
                    content_text=None, 
                    media_url=local_path, # Save the local file path
                    post_url=f"https://www.instagram.com/stories/{username}/", 
                    author_username=username
                )
                saved_count += 1
        
        logging.info(f"[Story Collector] Saved {saved_count} new story items to DB.")


async def fetch_post_data_via_graphql(shortcode: str, client: httpx.AsyncClient) -> dict:
    """
    Fetches post/reel data using the internal GraphQL API.
    This is based on the 'Method 2' from ahmedrangel/instagram-media-scraper.
    """
    logging.info(f"  > [GraphQL] Fetching post data for {shortcode}...")
    
    if not config.IG_APP_ID:
        logging.error("  > [GraphQL] FATAL: IG_APP_ID not configured in .env.")
        return {}

    # These params are from the scraper_graphql.js
    graphql_url = "https://www.instagram.com/api/graphql"
    params = {
        "variables": json.dumps({"shortcode": shortcode}),
        "doc_id": "10015901848480474",
        "lsd": "AVqbxe3J_YA", # This appears to be a static value
    }
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36",
        "Content-Type": "application/x-www-form-urlencoded",
        "X-IG-App-ID": config.IG_APP_ID,
        "X-FB-LSD": "AVqbxe3J_YA",
        "X-ASBD-ID": "129477",
        "Sec-Fetch-Site": "same-origin"
    }

    try:
        response = await client.post(graphql_url, data=params, headers=headers)
        
        if response.status_code != 200:
            logging.warning(f"  > [GraphQL] Failed to fetch {shortcode}. Status: {response.status_code}")
            return {}

        data = response.json()
        items = data.get("data", {}).get("xdt_shortcode_media")

        if not items:
            logging.warning(f"  > [GraphQL] No items found in response for {shortcode}.")
            return {}

        # Extract the key data we need
        caption_edge = items.get("edge_media_to_caption", {}).get("edges", [])
        return {
            "video_url": items.get("video_url"),
            "caption": caption_edge[0]["node"]["text"] if caption_edge else "",
            "product_type": items.get("product_type"),
        }

    except Exception as e:
        logging.error(f"  > [GraphQL] Error fetching {shortcode}: {e}")
        return {}
# --- END NEW FUNCTION ---



async def scrape_instagram_target(target_id: int, username: str, skip_stories=False, skip_posts=False):
    """
    SCRAPER MODE: "GATHER-THEN-JUMP" (V1.6 - Human Click Fix)
    """
    logging.info(f"[Smart Scraper] Starting Instagram scrape for: {username} (ID: {target_id})")
    
    async with async_playwright() as p:
        
        logging.info("Launching in HEADED mode (visible browser).")
        browser = await p.chromium.launch(
            headless=False, 
            args=["--disable-gpu"],
            slow_mo=50 
        )
        
        # --- 1. LOGIN & SESSION ---
        if not os.path.exists(AUTH_FILE):
            if not await login_to_instagram(browser):
                await browser.close()
                return False 
        
        context = await browser.new_context(
            storage_state=AUTH_FILE,
            viewport={'width': 1280, 'height': 800},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
        )
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

        # --- 2. START STORY SCRAPING (with CLI flag) ---
        profile_url = f"https://www.instagram.com/{username}/"
        if not skip_stories:
            await page.goto(profile_url) 
            await scrape_instagram_stories(page, target_id, username) 
        else:
            logging.info("[CLI] Skipping story scraping.")

# --- 3. GATHER ALL POSTS (with CLI flag) ---
        if not skip_posts:
            await page.goto(profile_url)

            posts_to_scrape = [] # This will be a list of (post_url, shortcode)
            try:
                try:
                    dismiss_button = page.locator('svg[aria-label="Dismiss"]').first
                    await dismiss_button.wait_for(state="visible", timeout=5000)
                    await dismiss_button.click()
                    logging.info("Dismissed 'Messages' popup.")
                except Exception:
                    logging.info("No 'Messages' popup found.")
                
                logging.info("Simulating human scrolling to load post grid...")
                for i in range(3):
                    await page.evaluate("window.scrollBy(0, 1500)") 
                    logging.info(f"Scroll {i+1}/3... waiting...")
                    await page.wait_for_timeout(random.randint(1500, 2500))

                logging.info("Gathering all post links from grid...")
                post_links_selector = 'a[href*="/p/"], a[href*="/reel/"]'
                post_elements = await page.locator(post_links_selector).all()
                
                if not post_elements:
                    logging.error(f"No posts found for {username}.")
                else:
                    logging.info(f"Found {len(post_elements)} post items on the grid.")
                    for el in post_elements:
                        try:
                            href = await el.get_attribute("href")
                            if not href: continue
                            
                            # Use regex to find the shortcode
                            post_id_match = re.search(r"/(p|reel)/([^/]+)", href)
                            if not post_id_match: continue
                            
                            shortcode = post_id_match.group(2)
                            post_url = f"https://www.instagram.com{href}"
                            
                            posts_to_scrape.append((post_url, shortcode))
                        except Exception as e:
                            logging.warning(f"Could not extract post info from grid: {e}")

            except Exception as e:
                logging.error(f"[Collector] Error gathering posts from {username}: {e}")
                await page.screenshot(path="debug_gather_failure.png")

            # --- 4. ANALYZE & GRAPHQL (NEW LOGIC) ---
            # This is much faster. No browser interaction needed.
            logging.info(f"--- Analyzing {len(posts_to_scrape)} potential posts using {len(AD_KEYWORDS)} keywords ---")
            
            saved_count = 0
            # Create one HTTP client for all requests
            async with httpx.AsyncClient() as client:
                for post_url, post_id in posts_to_scrape:
                    
                    if database.content_exists(post_id):
                        logging.info(f"Post {post_id} already in DB. Skipping API call.")
                        continue
                    
                    # Fetch post data (caption, video_url) from GraphQL API
                    post_data = await fetch_post_data_via_graphql(post_id, client)
                    
                    caption = post_data.get("caption", "").lower()
                    video_url = post_data.get("video_url")
                    
                    # Run our ad-keyword filter on the *real* caption
                    if not any(keyword.lower() in caption for keyword in AD_KEYWORDS):
                        logging.info(f"[Skipping] '{post_url}' (No ad keywords in caption)")
                        continue
                    
                    # If it's an ad, but not a video, we skip (for now)
                    if not video_url:
                        logging.warning(f"[Skipping] '{post_url}' (Ad match, but no video_url found in API response)")
                        continue

                    logging.info(f"[TARGET FOUND] '{post_url}' (Reason: caption match)")
                    
                    # Download the video bytes
                    try:
                        logging.info(f"  > Downloading video for {post_id}...")
                        video_response = await client.get(video_url, timeout=30.0)
                        video_response.raise_for_status() # Fail on 4xx/5xx
                        
                        video_bytes = video_response.content
                        content_type = post_data.get("product_type", "reel") # e.g., "clips"
                        
                        local_path = MEDIA_DIR / f"{post_id}.mp4"
                        with open(local_path, "wb") as f:
                            f.write(video_bytes)
                        logging.info(f"  > Video saved to: {local_path}")
                        
                        # Save to DB
                        database.save_content(
                            target_id=target_id,
                            platform='instagram',
                            post_id=post_id,
                            content_type=content_type, 
                            content_text=caption.strip(),
                            media_url=str(local_path), # <-- Save the LOCAL path
                            post_url=post_url,
                            author_username=username
                        )
                        logging.info(f"[Collector] Saved new {content_type}: {post_id} for {username}")
                        saved_count += 1
                        
                    except Exception as e:
                        logging.error(f"  > Failed to download or save video {post_id}: {e}")
                        await page.screenshot(path=f"debug_video_download_fail_{post_id}.png")

            logging.info(f"GraphQL Scrape complete for {username}. Saved {saved_count} new items.")
        
        else:
            logging.info("[CLI] Skipping post scraping.")

        # --- 5. CLEANUP ---
        await context.close()
        await browser.close()
        logging.info("Browser closed. Task finished.")



# This block allows us to run and test this file directly
async def main():
    # --- NEW: CLI Argument Parser ---
    parser = argparse.ArgumentParser(description="NFPInfluencers Instagram Scraper")
    parser.add_argument(
        "--no-stories",
        action="store_true", # This makes it a True/False flag
        help="Do not scrape 24-hour stories."
    )
    parser.add_argument(
        "--no-posts",
        action="store_true",
        help="Do not scrape posts/reels."
    )
    args = parser.parse_args()
    # --- END NEW: CLI Argument Parser ---

    logging.info("--- [DIRECT TEST MODE] ---")
    
    if not config.validate_config(required_keys=["IG_USERNAME", "IG_PASSWORD", "IG_APP_ID"]):
        logging.error("CRITICAL: IG_USERNAME and IG_PASSWORD not in .env. Exiting.")
        exit(1)

    logging.info("Testing Collector: Scraping target 'natgeo'...")
    
    target = database.get_target_by_name("natgeo")
    if not target:
        logging.warning("Test target 'natgeo' not in database. Adding it for this test.")
        database.add_target("natgeo", "instagram")
        target = database.get_target_by_name("natgeo")
        
    if not target:
        logging.error("Failed to add or get target. Exiting test.")
        return

    # Pass the CLI flags to the main function
    await scrape_instagram_target(
        target_id=target['id'], 
        username=target['username'],
        skip_stories=args.no_stories,
        skip_posts=args.no_posts
    )
    
    logging.info("Collector test done. Check data/surveillance.db.")


if __name__ == "__main__":
    asyncio.run(main())