#!/usr/bin/env python3
import os
import re
import sys
import asyncio
from github import Github
from rebrowser_playwright.async_api import async_playwright

GITHUB_TOKEN = os.environ["GITHUB_TOKEN"]
REPO_NAME = "JackisG/epg"
FILE_PATH = "languages/lit.m3u"
TARGET_URL = "https://freeiptv2023-d.ottc.xyz/index.php?action=view"

async def fetch_new_credentials():
    print("🌐 Launching rebrowser-playwright with stealth...")
    async with async_playwright() as p:
        # Extra args to avoid detection
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled",
                "--disable-features=IsolateOrigins,site-per-process"
            ]
        )
        context = await browser.new_context(
            viewport={"width": 1280, "height": 720},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = await context.new_page()

        # Stealth init script
        await page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            delete window.__playwright__binding__;
            delete window.__pwInitScripts;
            window.chrome = { runtime: {} };
        """)

        print("🔗 Navigating...")
        await page.goto(TARGET_URL, wait_until="networkidle", timeout=90000)

        # Wait up to 40 seconds for Turnstile to solve automatically
        try:
            await page.wait_for_selector("#accUser", timeout=40000)
        except Exception:
            # Dump page for debugging
            content = await page.content()
            print("⚠️ Page content (first 1000 chars):")
            print(content[:1000])
            raise Exception("Turnstile not solved. Try again later or use 2Captcha.")

        username = await page.get_attribute("#accUser", "value")
        password = await page.get_attribute("#accPass", "value")
        print(f"👤 Username: {username}")
        print(f"🔑 Password: {password}")
        await browser.close()
        return username, password

def update_m3u_file(username, password):
    # ... (identical to previous versions, omitted for brevity)

def main():
    try:
        user, pwd = asyncio.run(fetch_new_credentials())
        update_m3u_file(user, pwd)
        print("🎉 Done!")
    except Exception as e:
        print(f"❌ ERROR: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()