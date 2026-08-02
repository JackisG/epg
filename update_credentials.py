#!/usr/bin/env python3
import os
import re
import asyncio
from github import Github
from cloakbrowser import launch  # Drop-in replacement for Playwright

GITHUB_TOKEN = os.environ["GITHUB_TOKEN"]
REPO_NAME = "JackisG/epg"
FILE_PATH = "languages/lit.m3u"
TARGET_URL = "https://freeiptv2023-d.ottc.xyz/index.php?action=view"

async def fetch_new_credentials():
    print("🌐 Launching CloakBrowser...")
    browser = await launch(
        headless=True,
        humanize=True,  # Human-like behavior
        args=["--no-sandbox"]
    )
    page = await browser.new_page()

    print("🔗 Navigating...")
    await page.goto(TARGET_URL, wait_until="networkidle", timeout=90000)

    try:
        await page.wait_for_selector("#accUser", timeout=40000)
    except Exception:
        content = await page.content()
        print("⚠️ Page content (first 1000 chars):")
        print(content[:1000])
        raise Exception("Turnstile not solved.")

    username = await page.get_attribute("#accUser", "value")
    password = await page.get_attribute("#accPass", "value")
    print(f"👤 Username: {username}")
    print(f"🔑 Password: {password}")
    await browser.close()
    return username, password

# update_m3u_file and main are the same as above