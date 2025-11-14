import asyncio
import logging
import os
import re
import random 
from playwright.async_api import async_playwright
# Use absolute import to correctly reference the 'core' module outside the 'tools' package
from ..core import config, database 

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
AUTH_FILE = config.AUTH_FILE

AD_KEYWORDS = [
    "#loveandwarfilm"
]


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

        # 1. Handle "Save Info?"
        try:
            await page.click('text="Not Now"', timeout=5000)
            logging.info("Clicked 'Not Now' (Save Info).")
            await page.wait_for_url("https://www.instagram.com/", timeout=10000)
        except Exception:
            logging.info("No 'Save Info' popup found, or already navigated. That's OK.")

        # 2. Handle "Turn on Notifications?"
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
    SCRAPER MODE 4: 24-HOUR STORY COLLECTOR
    Navigates to a profile and scrapes ONLY the 24-hour stories.
    It stops before scraping "Destacadas" (Highlights).
    """
    logging.info(f"[Story Collector] Starting 24-hour story scrape for: {username}")
    
    story_url_base = f"https://www.instagram.com/{username}/"
    # We rely on the calling function to navigate to the profile first
    
    try:
        # 1. Find and click the profile picture (the story ring)
        story_ring_selector = f'a[href*="/stories/{username}/"]'
        await page.wait_for_selector(story_ring_selector, timeout=5000)
        await page.locator(story_ring_selector).first.click()
        logging.info("Clicked profile story ring.")

        # 2. Wait for the story modal to open (URL change)
        await page.wait_for_url("https://www.instagram.com/stories/**", timeout=10000)
        logging.info("Story modal is open. Starting scrape loop...")
        
        # 3. Dismiss any popups that appear over the story (e.g. share suggestions)
        try:
            await page.locator('svg[aria-label="Cerrar"]').click(timeout=2000) 
            logging.info("Dismissed story popup.")
        except Exception:
            pass

        scraped_stories = set()
        loop_count = 0
        stories_saved = 0
        
        while True:
            # Random wait for human behavior
            await page.wait_for_timeout(random.randint(2000, 3500))
            
            current_url = page.url

            # --- NEW STRATEGY: Stop if it's a Highlight ---
            if "/stories/highlights/" in current_url:
                logging.info("[Story Collector] Detected a Highlight. Ending 24-hour story scrape.")
                break
            # --- END NEW STRATEGY ---
            
            # Story ID extraction is typically the second-to-last segment
            story_id_match = re.search(r"/stories/([^/]+)/([^/]+)/", current_url)
            
            if not story_id_match or story_id_match.group(1) == "highlights":
                if loop_count > 5:
                    logging.info("Story URL pattern lost after 5 attempts. Assuming end of stories.")
                    break
                loop_count += 1
                await page.wait_for_timeout(1000)
                continue
                
            story_id = story_id_match.group(2)
            unique_story_id = f"story_{story_id}" 

            if unique_story_id in scraped_stories or database.content_exists(unique_story_id):
                logging.info(f"Story {unique_story_id} already processed or in DB. Clicking next.")
            else:
                # --- Media Extraction for Story ---
                media_url = None
                content_type = 'story_image'
                
                # We need a small delay here to let the media load
                await page.wait_for_timeout(500)

                try:
                    # 1. Try to get the video element source
                    video_element = page.locator('video[playsinline]').first
                    media_url = await video_element.get_attribute("src", timeout=1000)
                    content_type = 'story_video'
                except Exception:
                    # 2. Fallback to image element source
                    try:
                        img_element = page.locator('img[decoding="sync"]').first
                        media_url = await img_element.get_attribute("src", timeout=1000)
                        content_type = 'story_image'
                    except Exception:
                        logging.warning(f"Could not extract media for story {unique_story_id}")

                if media_url:
                    database.save_content(
                        target_id=target_id,
                        platform='instagram',
                        post_id=unique_story_id,
                        content_type=content_type,
                        content_text=None, # Stories rarely have accessible caption text
                        media_url=media_url,
                        post_url=current_url,
                        author_username=username
                    )
                    logging.info(f"[Collector] Saved new story: {unique_story_id}")
                    scraped_stories.add(unique_story_id)
                    stories_saved += 1
            
            # --- Navigate to Next Story ---
            try:
                # Use keyboard press for language independence and reliability
                await page.keyboard.press('ArrowRight')
                logging.info("Simulated ArrowRight key press.")
            except Exception:
                logging.info("Failed to simulate key press. Assuming end of stories.")
                break 

            if loop_count > 100: # Safety break just in case
                logging.warning("Story scrape hit 100 loops. Breaking loop to prevent infinite run.")
                break
            loop_count += 1

        logging.info(f"[Story Collector] Finished. Scraped {stories_saved} new 24-hour stories.")

    except Exception as e:
        if "timeout" in str(e).lower() and "stories" in str(e).lower():
            logging.info(f"[Story Collector] No visible story ring found for {username} (No 24h stories). Skipping.")
        else:
            logging.error(f"[Story Collector] Unhandled error scraping stories for {username}: {e}")
            await page.screenshot(path="debug_story_failure.png")


async def scrape_instagram_target(target_id: int, username: str):
    """
    SCRAPER MODE 3: "GATHER-THEN-JUMP" (V1.3 - Final Collector)
    
    1.  Runs Story Collector (24-hour only).
    2.  GATHERS all post URLs + alt text from the profile grid.
    3.  ANALYZES alt text for ad-related keywords.
    4.  JUMPS directly to high-value posts to scrape media, including carousels.
    """
    logging.info(f"[Smart Scraper] Starting Instagram scrape for: {username} (ID: {target_id})")
    
    async with async_playwright() as p:
        
        logging.info("Launching in HEADED mode (visible browser).")
        browser = await p.chromium.launch(
            headless=False, 
            args=["--disable-gpu"],
            # Add human-like delay to every action
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
            # Set a real User Agent to look less like a bot
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

        # --- 2. START STORY SCRAPING ---
        profile_url = f"https://www.instagram.com/{username}/"
        await page.goto(profile_url) # Start on the profile page
        
        # This will run the full 24-hour story scrape
        await scrape_instagram_stories(page, target_id, username) 

        # We must navigate back to the profile page before scraping posts
        await page.goto(profile_url)

        # --- 3. GATHER ALL POSTS ---
        posts_to_scrape = []
        try:
            # Dismiss any "Messages" popups (they can reappear after story viewer)
            try:
                dismiss_button = page.locator('svg[aria-label="Dismiss"]').first
                await dismiss_button.wait_for(state="visible", timeout=5000)
                await dismiss_button.click()
                logging.info("Dismissed 'Messages' popup.")
            except Exception:
                logging.info("No 'Messages' popup found.")
            
            logging.info("Simulating human scrolling to load post grid...")
            for i in range(3): # Scroll 3 times
                await page.evaluate("window.scrollBy(0, 1500)") 
                logging.info(f"Scroll {i+1}/3... waiting...")
                await page.wait_for_timeout(random.randint(1500, 2500))

            logging.info("Gathering all post links and alt texts from grid...")
            
            post_links_selector = 'a[href*="/p/"], a[href*="/reel/"]'
            
            post_elements = await page.locator(post_links_selector).all()
            
            if not post_elements:
                logging.error(f"No posts found for {username}. Profile might be private or empty.")
                # We skip the rest of the post-scrape loop but continue to cleanup
            else:
                logging.info(f"Found {len(post_elements)} post items on the grid.")
                
                for el in post_elements:
                    try:
                        href = await el.get_attribute("href")
                        if not href:
                            continue
                        
                        post_url = f"https://www.instagram.com{href}"
                        
                        img_element = el.locator('img')
                        alt_text = await img_element.get_attribute("alt")
                        
                        if not alt_text:
                            alt_text = "No alt text found on grid."
                            
                        posts_to_scrape.append((post_url, alt_text))
                        
                    except Exception as e:
                        logging.warning(f"Could not extract post info from grid: {e}")

        except Exception as e:
            logging.error(f"[Collector] Error gathering posts from {username}: {e}")
            await page.screenshot(path="debug_gather_failure.png")
            # We skip the rest of the post-scrape loop but continue to cleanup

        # --- 4. ANALYZE & JUMP ---
        logging.info(f"--- Analyzing {len(posts_to_scrape)} potential posts using {len(AD_KEYWORDS)} keywords ---")
        
        filtered_posts = []
        for post_url, alt_text in posts_to_scrape:
            if any(keyword in alt_text.lower() for keyword in AD_KEYWORDS):
                logging.info(f"[TARGET FOUND] '{post_url}' (Reason: alt text match)")
                filtered_posts.append((post_url, alt_text))
            else:
                logging.info(f"[Skipping] '{post_url}' (No ad keywords in alt text)")
        
        logging.info(f"--- Found {len(filtered_posts)} posts to scrape. Starting scrape... ---")
        
        saved_count = 0
        for post_url, alt_text in filtered_posts:
            try:
                post_id_match = re.search(r"/(p|reel)/([^/]+)", post_url)
                if not post_id_match:
                    continue
                
                post_id = post_id_match.group(2)
                if database.content_exists(post_id):
                    logging.info(f"Post {post_id} already in DB. Skipping full scrape.")
                    continue

                # --- JJUMP: Go directly to the post page ---
                logging.info(f"Jumping to post: {post_url}")
                await page.goto(post_url)
                
                # Wait for page to be interactive (e.g., comment box is visible)
                try:
                    logging.info("  > Waiting for post page to load...")
                    comment_box_selector = 'textarea'
                    await page.wait_for_selector(comment_box_selector, timeout=10000)
                    logging.info("  > Post page is loaded.")
                except Exception:
                    logging.warning("  > Could not find comment box, page may be broken. Continuing...")

                # Get full caption (h1)
                content_text = alt_text # Default to alt_text
                try:
                    caption_element = page.locator('h1').first
                    await caption_element.wait_for(state="visible", timeout=10000)
                    content_text = await caption_element.text_content()
                except Exception:
                    logging.info("  > No h1 caption found, using grid alt_text.")

                # --- CAROUSEL & MEDIA LOGIC ---
                next_button_selector = 'button._afxw._al46._al47'
                
                carousel_media_saved = 0
                saved_media_urls = set()

                try:
                    # --- A. TRY CAROUSEL LOGIC ---
                    await page.locator(next_button_selector).wait_for(state="visible", timeout=2000)
                    logging.info("  > Carousel post detected. Starting carousel scrape...")
                    
                    is_carousel = True
                    slide_index = 0
                    
                    while is_carousel:
                        slide_post_id = f"{post_id}-{slide_index}"
                        
                        if database.content_exists(slide_post_id):
                            logging.info(f"  > Slide {slide_post_id} already in DB. Clicking next.")
                        else:
                            media_url = None
                            content_type = 'post'
                            
                            try:
                                # --- TRY VIDEO FIRST ---
                                video_elements = await page.locator('video[src^="https"]').all()
                                for el in video_elements:
                                    if await el.is_visible():
                                        media_url = await el.get_attribute("src")
                                        content_type = 'reel'
                                        break
                                if not media_url:
                                    raise Exception("No visible video found")
                                    
                            except Exception:
                                # --- FALLBACK TO IMAGE ---
                                try:
                                    img_elements = await page.locator('img[style*="object-fit"]').all()
                                    for el in img_elements:
                                        if await el.is_visible():
                                            img_src = await el.get_attribute("src")
                                            if img_src and "scontent" in img_src: 
                                                media_url = img_src
                                                content_type = 'post'
                                                break
                                    if not media_url:
                                        raise Exception("No visible content image found")
                                except Exception as e:
                                    logging.warning(f"  > Could not extract media for slide {slide_index}: {e}")
                                    media_url = None

                            if media_url and media_url not in saved_media_urls:
                                database.save_content(
                                    target_id=target_id,
                                    platform='instagram',
                                    post_id=slide_post_id,
                                    content_type=content_type,
                                    content_text=content_text.strip(),
                                    media_url=media_url,
                                    post_url=post_url,
                                    author_username=username
                                )
                                logging.info(f"[Collector] Saved new {content_type} (slide {slide_index}): {slide_post_id}")
                                saved_media_urls.add(media_url)
                                carousel_media_saved += 1
                            elif not media_url:
                                logging.warning(f"  > No media URL found for slide {slide_index}")
                            else:
                                logging.warning(f"  > Duplicate media URL found for slide {slide_index}. Skipping save.")

                        # --- Click Next or End Loop ---
                        try:
                            next_button = page.locator(next_button_selector)
                            if await next_button.is_visible():
                                await next_button.click()
                                logging.info(f"  > Clicked next slide ({slide_index+1})")
                                await page.wait_for_timeout(random.randint(800, 1500))
                                slide_index += 1
                            else:
                                is_carousel = False
                                logging.info("  > End of carousel (next button hidden).")
                        except Exception:
                            is_carousel = False
                            logging.info("  > End of carousel (next button not found).")
                    
                    if carousel_media_saved > 0:
                        saved_count += carousel_media_saved

                except Exception:
                    # --- B. FALLBACK TO SINGLE MEDIA LOGIC ---
                    logging.info("  > Single media post detected. Running standard scrape...")
                    media_url = None
                    content_type = 'post'
                    
                    try:
                        # --- THE VIDEO FIX ---
                        video_element = page.locator('video')
                        await video_element.wait_for(
                            lambda el: el.get_attribute("src") and el.get_attribute("src").startswith("https."),
                            timeout=8000
                        )
                        media_url = await video_element.get_attribute("src")
                        content_type = 'reel'
                        logging.info(f"  > Captured Reel URL.")
                        
                    except Exception:
                        # --- FALLBACK TO IMAGE ---
                        logging.info("  > No video found. Checking for image.")
                        try:
                            img_element = page.locator('img[style*="object-fit"]').first
                            media_url = await img_element.get_attribute("src")
                            content_type = 'post'
                            logging.info(f"  > Captured Image URL.")
                        except Exception as e:
                            logging.warning(f"  > Could not extract any media for {post_id}: {e}")

                    # --- SAVE LOGIC FOR SINGLE MEDIA ---
                    if not media_url:
                        logging.warning(f"  > No media_url found for {post_id}. Skipping save.")
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
                
            except Exception as e:
                logging.error(f"  > Failed to scrape post page {post_url}: {e}")
                await page.screenshot(path=f"debug_post_failure_{post_id}.png")

        logging.info(f"Smart Scrape complete for {username}. Saved {saved_count} new items.")

        # --- 5. CLEANUP ---
        await context.close()
        await browser.close()
        logging.info("Browser closed. Task finished.")


# This block allows us to run and test this file directly
async def main():
    logging.info("--- [DIRECT TEST MODE] ---")
    
    if not config.validate_config(required_keys=["IG_USERNAME", "IG_PASSWORD"]):
        logging.error("CRITICAL: IG_USERNAME and IG_PASSWORD not in .env. Exiting.")
        exit(1)

    logging.info("Testing Collector: Scraping target 'natgeo'...")
    # We add a test target if it doesn't exist
    target = database.get_target_by_name("natgeo")
    if not target:
        logging.warning("Test target 'natgeo' not in database. Adding it for this test.")
        database.add_target("natgeo", "instagram")
        target = database.get_target_by_name("natgeo")
        
    await scrape_instagram_target(target['id'], target['username'])
    logging.info("Collector test done. Check data/surveillance.db.")


if __name__ == "__main__":
    asyncio.run(main())