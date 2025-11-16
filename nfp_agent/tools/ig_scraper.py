import asyncio
import logging
import os
import re
import random 
import argparse
import json
import httpx
from pathlib import Path
from playwright.async_api import async_playwright
# Use absolute import to correctly reference the 'core' module outside the 'tools' package
from ..core import config, database 

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
AUTH_FILE = config.AUTH_FILE

# --- FIXED TEST TARGET (from user) ---
AD_KEYWORDS = [
    "#GrowingUpAnimal",
    "@debeersgroup"
]
# --- END FIXED TEST TARGET ---

# --- GLOBAL MEDIA DIR ---
MEDIA_DIR = config.BASE_DIR / "data" / "media"
os.makedirs(MEDIA_DIR, exist_ok=True)


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

# --- NEW FUNCTION 2: The Story Scraper ---
async def fetch_stories_via_api(target_id: int, username: str, client: httpx.AsyncClient):
    """
    Scrapes all current stories for a target using the internal v1 API.
    This replaces the entire Playwright-based story scraper.
    """
    logging.info(f"[Story Collector] Starting API-based story scrape for: {username}")
    
    # 1. Get the numerical user_id
    user_id = await get_user_id_from_username(username, client)
    if not user_id:
        return

    # 2. Hit the internal story feed API
    # This requires the full auth cookie, which is in the client headers
    story_url = f"https://www.instagram.com/api/v1/feed/user/{user_id}/story/"
    
    try:
        response = await client.get(story_url)
        response.raise_for_status()
        data = response.json()
        
        items = data.get("reel", {}).get("items", [])
        if not items:
            logging.info(f"[Story Collector] No stories found for {username}.")
            return

        logging.info(f"[Story Collector] Found {len(items)} story items. Downloading...")
        saved_count = 0
        
        for item in items:
            post_id = item.get("pk") # Use 'pk' as the unique ID
            if not post_id:
                continue
                
            if database.content_exists(post_id):
                logging.info(f"  > Story {post_id} already in DB. Skipping.")
                continue

            media_url = None
            content_type = "story_image"
            extension = ".jpg" # Default
            
            if item.get("video_versions"):
                media_url = item["video_versions"][0]["url"]
                content_type = "story_video"
                extension = ".mp4"
            elif item.get("image_versions2"):
                media_url = item["image_versions2"]["candidates"][0]["url"]
                content_type = "story_image"
                extension = ".jpg"
            
            if not media_url:
                logging.warning(f"  > No media_url found for story {post_id}. Skipping.")
                continue
                
            # Download the asset bytes
            try:
                media_response = await client.get(media_url, timeout=30.0)
                media_response.raise_for_status()
                
                local_path = MEDIA_DIR / f"{post_id}{extension}"
                with open(local_path, "wb") as f:
                    f.write(media_response.content)
                
                # Save to DB
                database.save_content(
                    target_id=target_id,
                    platform='instagram',
                    post_id=post_id,
                    content_type=content_type,
                    content_text=None, # Stories have no captions
                    media_url=str(local_path), # Save the LOCAL path
                    post_url=f"https://www.instagram.com/stories/{username}/{post_id}/",
                    author_username=username
                )
                logging.info(f"  > [API] Saved {content_type}: {post_id} to {local_path}")
                saved_count += 1
                
            except Exception as e:
                logging.error(f"  > [API] Failed to download story asset {post_id}: {e}")

        logging.info(f"[Story Collector] Saved {saved_count} new story items to DB.")

    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            logging.info(f"[Story Collector] No stories found for {username} (404).")
        else:
            logging.error(f"[Story Collector] Error fetching story feed for {username}: {e}")
    except Exception as e:
        logging.error(f"[Story Collector] Error processing story feed for {username}: {e}")


# --- REVISED FUNCTION 3: GraphQL Post Fetcher (FIXED) ---
async def fetch_post_data_via_graphql(shortcode: str, client: httpx.AsyncClient) -> dict:
    """
    Fetches post/reel data using the internal GraphQL API.
    Based on ahmedrangel/instagram-media-scraper.
    """
    logging.info(f"  > [GraphQL] Fetching post data for {shortcode}...")
    
    if not config.IG_APP_ID:
        logging.error("  > [GraphQL] FATAL: IG_APP_ID not configured in .env.")
        return {}

    graphql_url = "https://www.instagram.com/api/graphql"
    params = {
        "variables": json.dumps({"shortcode": shortcode}),
        "doc_id": "10015901848480474", # Static doc_id from scraper.js
        "lsd": "AVqbxe3J_YA",
    }
    
    # --- THIS IS THE FIX ---
    # We start with the client's existing headers (which has the Cookie)
    # and then add the new ones needed for this specific request.
    merged_headers = dict(client.headers)
    merged_headers.update({
        "Content-Type": "application/x-www-form-urlencoded",
        "X-FB-LSD": "AVqbxe3J_YA",
        "X-ASBD-ID": "129477",
        "Sec-Fetch-Site": "same-origin"
    })
    # --- END THE FIX ---

    try:
        # Use the new 'merged_headers'
        response = await client.post(graphql_url, data=params, headers=merged_headers)
        response.raise_for_status()
        
        data = response.json()
        items = data.get("data", {}).get("xdt_shortcode_media")

        if not items:
            logging.warning(f"  > [GraphQL] No items found in response for {shortcode}.")
            return {}

        caption_edge = items.get("edge_media_to_caption", {}).get("edges", [])
        return {
            "video_url": items.get("video_url"),
            "caption": caption_edge[0]["node"]["text"] if caption_edge else "",
            "product_type": items.get("product_type"),
        }

    except Exception as e:
        # Now, this error will be more specific if it's not a JSON error
        logging.error(f"  > [GraphQL] Error fetching {shortcode}: {e}")
        return {}


# --- REWRITTEN MAIN FUNCTION ---
async def scrape_instagram_target(target_id: int, username: str, skip_stories=False, skip_posts=False):
    """
    SCRAPER MODE: "HYBRID API" (V2.0 - Robust)
    Uses Playwright ONLY to log in, then scrapes all data via
    direct API calls using the authenticated session.
    """
    logging.info(f"[Hybrid Scraper] Starting scrape for: {username} (ID: {target_id})")
    
    async with async_playwright() as p:
        
        # --- 1. LOGIN & SESSION ---
        logging.info("Launching browser to get auth session...")
        browser = await p.chromium.launch(
            headless=False, # Must be headed for first login
            slow_mo=50 
        )
        
        if not os.path.exists(AUTH_FILE):
            if not await login_to_instagram(browser):
                await browser.close()
                return False 
        
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

        # --- 2. CREATE THE API CLIENT ---
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
        
        # We can now close the browser
        await context.close()
        await browser.close()
        logging.info("Browser closed. Proceeding with API-only scraping.")

        # --- 3. START SCRAPING (using the API client) ---
        async with httpx.AsyncClient(headers=api_headers, follow_redirects=True, timeout=30.0) as client:

            # --- 4. START STORY SCRAPING (NEW API METHOD) ---
            if not skip_stories:
                await fetch_stories_via_api(target_id, username, client)
            else:
                logging.info("[CLI] Skipping story scraping.")

            # --- 5. GATHER ALL POSTS (GRAPHQL METHOD) ---
            if not skip_posts:
                logging.info("[Post Scraper] Launching lightweight browser to gather post links...")
                browser = await p.chromium.launch(headless=False, slow_mo=50) # Headed to avoid detection
                context = await browser.new_context(storage_state=AUTH_FILE)
                page = await context.new_page()
                
                await page.goto(f"https://www.instagram.com/{username}/")
                
                posts_to_scrape = [] # (post_url, shortcode)
                try:
                    logging.info("Simulating human scrolling to load post grid...")
                    for i in range(3): # Scroll 3 times
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
                                
                                post_id_match = re.search(r"/(p|reel)/([^/]+)", href)
                                if not post_id_match: continue
                                
                                shortcode = post_id_match.group(2)
                                post_url = f"https://www.instagram.com{href}"
                                
                                # Add to list, avoid duplicates
                                if (post_url, shortcode) not in posts_to_scrape:
                                    posts_to_scrape.append((post_url, shortcode))
                            except Exception as e:
                                logging.warning(f"Could not extract post info from grid: {e}")
                
                except Exception as e:
                    logging.error(f"[Collector] Error gathering posts from {username}: {e}")
                    await page.screenshot(path="debug_gather_failure.png")
                
                await context.close()
                await browser.close()
                logging.info("Browser closed. Post links gathered.")

                # --- 6. ANALYZE & GRAPHQL (Uses our httpx client) ---
                logging.info(f"--- Analyzing {len(posts_to_scrape)} potential posts via GraphQL ---")
                
                saved_count = 0
                for post_url, post_id in posts_to_scrape:
                    
                    if database.content_exists(post_id):
                        logging.info(f"Post {post_id} already in DB. Skipping API call.")
                        continue
                    
                    post_data = await fetch_post_data_via_graphql(post_id, client)
                    
                    caption = post_data.get("caption", "").lower()
                    video_url = post_data.get("video_url")
                    
                    # Run ad-keyword filter
                    if not any(keyword.lower() in caption for keyword in AD_KEYWORDS):
                        logging.info(f"[Skipping] '{post_url}' (No ad keywords in caption)")
                        continue
                    
                    if not video_url:
                        logging.warning(f"[Skipping] '{post_url}' (Ad match, but no video_url)")
                        continue

                    logging.info(f"[TARGET FOUND] '{post_url}' (Reason: caption match)")
                    
                    try:
                        logging.info(f"  > Downloading video for {post_id}...")
                        video_response = await client.get(video_url, timeout=30.0)
                        video_response.raise_for_status()
                        
                        video_bytes = video_response.content
                        content_type = post_data.get("product_type", "reel")
                        
                        local_path = MEDIA_DIR / f"{post_id}.mp4"
                        with open(local_path, "wb") as f:
                            f.write(video_bytes)
                        logging.info(f"  > Video saved to: {local_path}")
                        
                        database.save_content(
                            target_id=target_id,
                            platform='instagram',
                            post_id=post_id,
                            content_type=content_type,
                            content_text=caption.strip(),
                            media_url=str(local_path),
                            post_url=post_url,
                            author_username=username
                        )
                        saved_count += 1
                        
                    except Exception as e:
                        logging.error(f"  > Failed to download or save video {post_id}: {e}")
            else:
                logging.info("[CLI] Skipping post scraping.")

        logging.info(f"Hybrid API Scrape complete for {username}.")


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
    
    # --- THIS IS THE UPDATE ---
    required_keys = ["IG_USERNAME", "IG_PASSWORD", "IG_APP_ID"]
    if not config.validate_config(required_keys=required_keys):
        logging.error(f"CRITICAL: {required_keys} not in .env. Exiting.")
        exit(1)
    # --- END UPDATE ---

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