import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        
        logs = []
        page.on("console", lambda msg: logs.append(msg.text))
        
        import os
        base_url = os.getenv("TRIDENT_BASE_URL", "http://127.0.0.1:8020")
        await page.goto(f"{base_url}/products")
        await page.wait_for_timeout(3000)
        
        print("Logs:", logs)
        grid_html = await page.evaluate("document.querySelector('[data-products-grid]')?.innerHTML")
        print("Grid HTML length:", len(grid_html) if grid_html else "None")
        count = await page.evaluate("document.querySelector('[data-product-count]')?.textContent")
        print("Count:", count)
        
        await browser.close()

asyncio.run(main())
