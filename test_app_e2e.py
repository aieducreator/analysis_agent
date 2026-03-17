# -*- coding: utf-8 -*-
import asyncio
from playwright.async_api import async_playwright
import time
import os

async def run(playwright):
    browser = await playwright.chromium.launch(headless=True)
    context = await browser.new_context(viewport={'width': 1280, 'height': 800})
    page = await context.new_page()

    print("Navigating to local Streamlit app...")
    await page.goto("http://localhost:8507")
    
    # Wait for the chat input to appear
    print("Waiting for chat input...")
    await page.wait_for_selector('textarea', timeout=30000)
    
    # Type the query
    query = "2024년 전체 기간 동안, '골목 상권' 유형의 상권들 중에서 30대 매출액 총합이 가장 높은 곳을 알려줘"
    print(f"Typing query: {query}")
    await page.fill('textarea', query)
    await page.keyboard.press('Enter')
    
    print("Waiting for AI response (this could take a while)...")
    # Wait for the markdown response mentioning "성수동카페거리". We can use a loop to check the text content.
    found = False
    for i in range(30):
        # We wait 2 seconds between checks
        await asyncio.sleep(2)
        content = await page.content()
        if "분석 완료" in content and "성수동카페거리" in content:
            found = True
            break
            
    if found:
        print("Verification SUCCESS: AI answered correctly.")
    else:
        print("Verification FAILED: AI answer did not contain expected text.")
        
    await asyncio.sleep(2)  # brief pause for rendering
    screenshot_path = os.path.join(os.getcwd(), 'verification_screenshot.png')
    await page.screenshot(path=screenshot_path)
    print(f"Screenshot saved to {screenshot_path}")

    await context.close()
    await browser.close()
    
    assert found, "Test failed!"

async def main():
    async with async_playwright() as playwright:
        await run(playwright)

if __name__ == '__main__':
    asyncio.run(main())
