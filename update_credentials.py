#!/usr/bin/env python3
import os
import re
import sys
import asyncio
from github import Github
from cloakbrowser import launch_async

GITHUB_TOKEN = os.environ["GITHUB_TOKEN"]
REPO_NAME = "JackisG/epg"
FILE_PATH = "languages/lit.m3u"
TARGET_URL = "https://freeiptv2023-d.ottc.xyz/index.php?action=view"

async def fetch_new_credentials():
    print("🌐 Launching CloakBrowser Pro (headed mode via xvfb)...")
    browser = await launch_async(
        headless=False,               # Headed mode – works better with Turnstile
        humanize=True,
        args=["--no-sandbox", "--disable-dev-shm-usage"],
        timeout=120000,
        # The license key is automatically picked up from the environment
    )
    page = await browser.new_page()

    print("🔗 Navigating to the page...")
    await page.goto(TARGET_URL, wait_until="domcontentloaded", timeout=120000)

    # Give extra time for Turnstile to solve
    await page.wait_for_timeout(5000)

    try:
        await page.wait_for_selector("#accUser", timeout=60000)
    except Exception:
        content = await page.content()
        print("⚠️ Page content (first 1000 chars):")
        print(content[:1000])
        raise Exception("Turnstile not solved – page didn't load credentials.")

    username = await page.get_attribute("#accUser", "value")
    password = await page.get_attribute("#accPass", "value")
    print(f"👤 New Username: {username}")
    print(f"🔑 New Password: {password}")
    await browser.close()
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

    # Correct pattern for path-based URLs
    pattern = re.compile(
        r'(http://freeiptv\.ottc\.xyz:[0-9]+/live/)\d+(/\d+/[^/\s]+)'
    )

    for line in lines:
        m = pattern.search(line)
        if m:
            base = m.group(1)
            rest = m.group(2)
            new_line = line.replace(m.group(0), f"{base}{username}{rest}")
            new_lines.append(new_line)
            replaced += 1
            print(f"🔄 Updated: {line[:80]}...")
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
        branch="master"
    )
    print(f"✅ Updated {replaced} URL(s).")

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