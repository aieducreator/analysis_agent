import asyncio
import os
from playwright.async_api import async_playwright

async def run(playwright):
    browser = await playwright.chromium.launch(headless=True)
    context = await browser.new_context()
    page = await context.new_page()

    print("Navigating to test app...")
    await page.goto("http://localhost:8505")
    
    # Wait for the button
    print("Clicking 'Test Pool' button...")
    await page.wait_for_selector('button:has-text("Test Pool")')
    await page.click('button:has-text("Test Pool")')
    
    # Wait for result
    try:
        await page.wait_for_selector('text="Query Result:"', timeout=10000)
        print("Success!")
    except Exception as e:
        print(f"Failed or timed out: {e}")
        
    await browser.close()

async def main():
    async with async_playwright() as playwright:
        await run(playwright)

if __name__ == '__main__':
    asyncio.run(main())
