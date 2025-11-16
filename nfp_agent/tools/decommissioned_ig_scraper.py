import asyncio
import logging
import os
import re
import random 
import argparse # For CLI options
from playwright.async_api import async_playwright, Page, BrowserContext

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
AUTH_FILE = config.AUTH_FILE

# --- FIXED TEST TARGET (from user) ---
AD_KEYWORDS = [
    "#GrowingUpAnimal",
    "@debeersgroup" # Case-insensitive check handles this
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


async def scrape_instagram_stories(page: Page, target_id: int, username: str):
    """
    SCRAPER MODE 5: "NETWORK INTERCEPT" (V1.8 - "Click-to-Open")
    This clicks the story and uses your human-like random wait.
    """
    logging.info(f"[Story Collector] Starting network intercept scrape for: {username}")
    
    intercepted_media = set() # Use a set to avoid duplicates

    def story_network_handler(request):
        """Listen for story media files"""
        url = request.url
        if "scontent" in url and ('.mp4' in url or '.jpg' in url) and "PREVIEW" not in url:
            if request.resource_type in ("media", "image", "other"):
                logging.info(f"  > [STORY NETWORK] Intercepted story media: {url[:70]}...")
                intercepted_media.add(url)

    page.on("request", story_network_handler)

    try:
# --- NEW, ROBUST CLICK SELECTOR (Based on your HTML screenshot) ---
        # We find the div with role="button" that contains the canvas (the story ring).
        profile_pic_selector = f'div[role="button"]:has(canvas)'
        logging.info(f"Looking for story button with selector: {profile_pic_selector}")            
        await page.wait_for_selector(profile_pic_selector, timeout=5000)
        await page.locator(profile_pic_selector).first.click()
        logging.info("Clicked profile picture to open stories.")

        # 2. Wait for story modal (This is the mandatory URL check you requested)
        await page.wait_for_url("https://www.instagram.com/stories/**", timeout=10000)
        logging.info("Story modal is open. Starting burst scrape...")

        # 3. Burst scrape: Click "Next" N times to trigger network requests
        stories_to_check = 15
        for i in range(stories_to_check):
            if "/stories/highlights/" in page.url:
                logging.info("[Story Collector] Detected a Highlight. Ending scrape.")
                break
            
            # Use the random wait as requested
            await page.wait_for_timeout(random.randint(1000, 2500)) 
            await page.keyboard.press('ArrowRight')
            logging.info(f"  > Clicked Next story ({i+1}/{stories_to_check})")
        
        logging.info(f"Burst scrape complete. Found {len(intercepted_media)} unique media items.")

    except Exception as e:
        # If the click or URL wait fails, this is where we end up.
        if "timeout" in str(e).lower() or "await page.wait_for_url" in str(e):
            logging.error("https://www.linguee.com.ar/ingles-espanol/traduccion/check+failed.html Story modal failed to open. Check credentials/locale.")
        else:
            logging.error(f"[Story Collector] Error scraping stories: {e}")
            await page.screenshot(path="debug_story_failure.png")
    
    finally:
        # 4. CRITICAL: Remove the listener
        page.remove_listener("request", story_network_handler)

        # 5. Save all unique media found
        saved_count = 0
        for i, media_url in enumerate(intercepted_media):
            # Create a unique ID based on the media URL hash
            post_id = f"story_{abs(hash(media_url))}"
            
            if not database.content_exists(post_id):
                content_type = 'story_video' if '.mp4' in media_url else 'story_image'
                
                database.save_content(
                    target_id=target_id,
                    platform='instagram',
                    post_id=post_id,
                    content_type=content_type,
                    content_text=None, # Correct argument name
                    media_url=media_url,
                    post_url=f"https://www.instagram.com/stories/{username}/", # Generic URL
                    author_username=username
                )
                saved_count += 1
        
        logging.info(f"[Story Collector] Saved {saved_count} new story items to DB.")


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
            user_agent="Mozilla.5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
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
            await page.goto(profile_url) # Go back to profile

            posts_to_scrape = []
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

                logging.info("Gathering all post links and alt texts from grid...")
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
                            post_url = f"https://www.instagram.com{href}"
                            img_element = el.locator('img')
                            alt_text = await img_element.get_attribute("alt")
                            
                            alt_text = alt_text if alt_text else "no alt text"
                            
                            posts_to_scrape.append((post_url, alt_text))
                        except Exception as e:
                            logging.warning(f"Could not extract post info from grid: {e}")

            except Exception as e:
                logging.error(f"[Collector] Error gathering posts from {username}: {e}")
                await page.screenshot(path="debug_gather_failure.png")

            # --- 4. ANALYZE & JUMP (Original "Gather then Jump" logic) ---
            logging.info(f"--- Analyzing {len(posts_to_scrape)} potential posts using {len(AD_KEYWORDS)} keywords ---")
            
            filtered_posts = []
            for post_url, alt_text in posts_to_scrape:
                # --- FINAL BUG FIX: Case-insensitive check on BOTH sides ---
                if any(keyword.lower() in alt_text.lower() for keyword in AD_KEYWORDS):
                    logging.info(f"[TARGET FOUND] '{post_url}' (Reason: alt text match)")
                    filtered_posts.append((post_url, alt_text))
                else:
                    logging.info(f"[Skipping] '{post_url}' (No ad keywords in alt text)")
            
            logging.info(f"--- Found {len(filtered_posts)} posts to scrape. Starting scrape... ---")
            
            saved_count = 0
            for post_url, alt_text in filtered_posts:
                network_handler = None 
                post_page = None
                try:
                    post_id_match = re.search(r"/(p|reel)/([^/]+)", post_url)
                    if not post_id_match: continue
                    
                    post_id = post_id_match.group(2)
                    content_type = 'reel' if '/reel/' in post_url else 'post'
                    
                    if database.content_exists(post_id):
                        logging.info(f"Post {post_id} already in DB. Skipping full scrape.")
                        continue

                    # --- NEW "NEW TAB" STRATEGY ---
                    logging.info(f"Opening post in new tab: {post_url}")
                    post_page = await context.new_page()
                    
                    media_url = None
                    content_type_from_intercept = None

                    def network_handler(request):
                        nonlocal media_url, content_type_from_intercept
                        if "scontent" in request.url and ".mp4" in request.url and request.resource_type == "media":
                            if not media_url: 
                                logging.info(f"  > [NETWORK] Intercepted video URL: {request.url}")
                                media_url = request.url
                                content_type_from_intercept = 'reel'

                    await post_page.on("request", network_handler)
                    
                    # Go to the post page in the new tab
                    await post_page.goto(post_url)
                    
                    try:
                        await post_page.wait_for_selector('textarea', timeout=10000)
                        logging.info("  > Post page is loaded. Waiting 10s for media...")
                        await post_page.wait_for_timeout(10000)
                    except Exception:
                        logging.warning("  > Could not find comment box, but continuing...")

                    await post_page.remove_listener("request", network_handler)
                    # --- END "NEW TAB" STRATEGY ---

                    content_text = alt_text # Default
                    try:
                        caption_element = post_page.locator('h1').first
                        await caption_element.wait_for(state="visible", timeout=10000)
                        content_text = await caption_element.text_content()
                    except Exception:
                        logging.info("  > No h1 caption found, using grid alt_text.")

                    next_button_selector = 'button._afxw._al46._al47'
                    is_carousel = False
                    try:
                        await post_page.locator(next_button_selector).wait_for(state="visible", timeout=2000)
                        is_carousel = True
                    except Exception:
                        is_carousel = False
                    
                    if is_carousel or not media_url:
                        if is_carousel:
                            logging.info("  > Carousel post detected. Using manual scrape for images/fallback...")
                        else:
                            logging.warning("  > Network intercept failed for reel. Falling back to thumbnail...")
                        try:
                            # Inside modal, the selector is different
                            img_elements = await post_page.locator('img[style*="object-fit"]').all()
                            for el in img_elements:
                                if await el.is_visible():
                                    img_src = await el.get_attribute("src")
                                    if img_src and "scontent" in img_src: 
                                        media_url = img_src
                                        break
                            if not media_url: raise Exception("No visible image")
                        except Exception as e:
                            logging.warning(f"  > Fallback scrape failed for {post_id}: {e}")
                    else:
                        logging.info("  > Network intercept successful.")
                        content_type = content_type_from_intercept

                    if not media_url:
                        logging.warning(f"  > No media_url found for {post_id}. Skipping save.")
                        await post_page.close()
                        continue
                        
                    database.save_content(
                        target_id=target_id,
                        platform='instagram',
                        post_id=post_id,
                        content_type=content_type, 
                        content_text=content_text.strip(),
                        media_url=media_url,
                        post_url=post_url,
                        author_username=username
                    )
                    logging.info(f"[Collector] Saved new {content_type}: {post_id} for {username}")
                    saved_count += 1
                    
                    # Close the tab
                    await post_page.close()
                    
                except Exception as e:
                    try:
                        if post_page: await post_page.close()
                        page.remove_listener("request", network_handler)
                    except Exception:
                        pass 
                    logging.error(f"  > Failed to scrape post page {post_url}: {e}")
                    await page.screenshot(path=f"debug_post_failure_{post_id}.png")

            logging.info(f"Smart Scrape complete for {username}. Saved {saved_count} new items.")
        else:
            logging.info("[CLI] Skipping post scraping.")

    # --- NO BROWSER CLEANUP - Main() will handle it ---


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
    
    if not config.validate_config(required_keys=["IG_USERNAME", "IG_PASSWORD"]):
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