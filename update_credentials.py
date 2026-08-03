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
    print("🌐 Launching rebrowser-playwright (stealth, no external solver)...")
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"]
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

        print("🔗 Navigating to page...")
        await page.goto(TARGET_URL, wait_until="domcontentloaded", timeout=60000)

        # Wait up to 60 seconds for the credentials to appear.
        # rebrowser-playwright will automatically handle Turnstile.
        try:
            await page.wait_for_selector("#accUser", timeout=60000)
        except Exception:
            content = await page.content()
            print("⚠️ Page content (first 1000 chars):")
            print(content[:1000])
            raise Exception("Credentials not found – rebrowser-playwright couldn't solve Turnstile.")

        username = await page.get_attribute("#accUser", "value")
        password = await page.get_attribute("#accPass", "value")
        print(f"👤 New Username: {username}")
        print(f"🔑 New Password: {password}")
        await browser.close()
        return username, password

# (update_m3u_file and main are the same as before – keep them)