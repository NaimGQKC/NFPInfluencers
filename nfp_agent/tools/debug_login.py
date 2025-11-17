import asyncio
import logging
from playwright.async_api import async_playwright

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

async def main():
    logging.info("Launching browser in headed mode...")
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,
            slow_mo=100
        )
        context = await browser.new_context()
        page = await context.new_page()
        
        logging.info("Navigating to Instagram login page...")
        await page.goto("https://www.instagram.com/accounts/login/")
        
        logging.info("--- BROWSER IS PAUSED ---")
        logging.info("Right-click and 'Inspect' the username/password fields.")
        logging.info("Find the new selectors (e.g., name, aria-label).")
        logging.info("Press Ctrl+C in this terminal to quit.")
        
        # This will pause the script indefinitely
        # allowing you to inspect the browser.
        await page.pause()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("Debug session ended.")