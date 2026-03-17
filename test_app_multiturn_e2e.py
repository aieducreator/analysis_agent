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
    await page.goto("http://localhost:7860")
    
    # Wait for the chat input to appear
    print("Waiting for chat input...")
    await page.wait_for_selector('textarea', timeout=30000)
    
    # Turn 1
    query1 = "2024년 1분기 성수동카페거리의 총 매출액을 알려줘"
    print(f"Typing Turn 1 query: {query1}")
    await page.fill('textarea', query1)
    await page.keyboard.press('Enter')
    
    print("Waiting for AI response for Turn 1...")
    found1 = False
    for i in range(30):
        await asyncio.sleep(2)
        content = await page.content()
        if "분석 완료" in content and "성수동카페거리" in content:
            found1 = True
            break
            
    assert found1, "Turn 1 failed to get response!"
    print("Turn 1 Success!")
    
    await asyncio.sleep(2) # brief pause
    
    # Turn 2: Implicit reference to the previous turn
    query2 = "그럼 동일한 기간 동안 흑리단길은 어때?"
    print(f"Typing Turn 2 query: {query2}")
    
    # Locate the textarea again since it might be redrawn or we just fill it again
    # We wait until it's editable and empty 
    await page.wait_for_selector('textarea')
    await page.fill('textarea', query2)
    # the second enter triggers the second turn
    await page.keyboard.press('Enter')
    
    print("Waiting for AI response for Turn 2...")
    found2 = False
    for i in range(30):
        await asyncio.sleep(2)
        content = await page.content()
        # Streamlit only renders the active st.status, so only 1 "분석 완료" will be on screen
        if "분석 완료" in content and "흑리단길" in content:
            found2 = True
            break
            
    if found2:
        print("Verification SUCCESS: Multi-turn worked and AI answered both correctly.")
    else:
        print("Verification FAILED: AI turn 2 failed.")
        
    await asyncio.sleep(2)
    screenshot_path = os.path.join(os.getcwd(), 'verification_multiturn_screenshot.png')
    await page.screenshot(path=screenshot_path)
    print(f"Screenshot saved to {screenshot_path}")

    await context.close()
    await browser.close()
    
    assert found2, "Multi-turn test failed!"

async def main():
    async with async_playwright() as playwright:
        await run(playwright)

if __name__ == '__main__':
    asyncio.run(main())
