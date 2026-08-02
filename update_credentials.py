#!/usr/bin/env python3
import os
import re
import sys
import traceback
import asyncio
from github import Github
from playwright.async_api import async_playwright
from playwright_stealth import stealth_async

GITHUB_TOKEN = os.environ["GITHUB_TOKEN"]
REPO_NAME = "JackisG/epg"
FILE_PATH = "languages/lit.m3u"
TARGET_URL = "https://freeiptv2023-d.ottc.xyz/index.php?action=view"

async def fetch_new_credentials():
    print("🌐 Launching browser...")
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox"])
        context = await browser.new_context()
        page = await context.new_page()
        await stealth_async(page)

        print("🔗 Navigating to page...")
        await page.goto(TARGET_URL, wait_until="networkidle", timeout=90000)

        try:
            await page.wait_for_selector("#accUser", timeout=30000)
        except Exception:
            content = await page.content()
            print("⚠️ Page content (first 1000 chars):")
            print(content[:1000])
            raise Exception("Could not find #accUser – page may be blocked.")

        username = await page.get_attribute("#accUser", "value")
        password = await page.get_attribute("#accPass", "value")
        print(f"👤 Username: {username}")
        print(f"🔑 Password: {password}")

        await browser.close()
        if not (username and password):
            raise Exception("Credentials not found.")
        return username, password

def update_m3u_file(username, password):
    print("📂 Connecting to GitHub...")
    g = Github(GITHUB_TOKEN)
    repo = g.get_repo(REPO_NAME)

    contents = repo.get_contents(FILE_PATH)
    current = contents.decoded_content.decode("utf-8")
    lines = current.splitlines()
    new_lines = []
    replaced = 0

    pattern = re.compile(
        r'(http://freeiptv\.ottc\.xyz:[0-9]+/(?:live|get\.php)\?.*?)(username=)\d+(.*?)(password=)\d+(.*)'
    )

    for line in lines:
        m = pattern.search(line)
        if m:
            new_line = f"{m.group(1)}{m.group(2)}{username}{m.group(3)}{m.group(4)}{password}{m.group(5)}"
            new_lines.append(new_line)
            replaced += 1
            print(f"🔄 Updated: {line[:60]}...")
        else:
            new_lines.append(line)

    if replaced == 0:
        print("⚠️ No 'freeiptv.ottc.xyz' URLs found – nothing changed.")
        return

    repo.update_file(
        path=FILE_PATH,
        message=f"Auto-update credentials: username={username}",
        content="\n".join(new_lines),
        sha=contents.sha,
        branch="master"   # change to "main" if needed
    )
    print(f"✅ Updated {replaced} URL(s) and pushed to GitHub.")

def main():
    try:
        user, pwd = asyncio.run(fetch_new_credentials())
        update_m3u_file(user, pwd)
        print("🎉 All done!")
    except Exception as e:
        print(f"❌ ERROR: {e}")
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
