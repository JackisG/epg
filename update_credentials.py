#!/usr/bin/env python3
import os
import re
import sys
import asyncio
from github import Github
from cloakbrowser import launch  # Drop-in replacement for Playwright

GITHUB_TOKEN = os.environ["GITHUB_TOKEN"]
REPO_NAME = "JackisG/epg"
FILE_PATH = "languages/lit.m3u"
TARGET_URL = "https://freeiptv2023-d.ottc.xyz/index.php?action=view"

async def fetch_new_credentials():
    print("🌐 Launching CloakBrowser (free, cloudflare solver)...")
    # Launch with human-like behavior and headless mode
    browser = await launch(
        headless=True,
        humanize=True,          # simulate human mouse/timing
        args=["--no-sandbox", "--disable-dev-shm-usage"],
        timeout=90000           # 90 seconds
    )
    page = await browser.new_page()

    print("🔗 Navigating to the page...")
    await page.goto(TARGET_URL, wait_until="networkidle", timeout=90000)

    # Wait for the credentials to appear (Turnstile is solved automatically)
    try:
        await page.wait_for_selector("#accUser", timeout=60000)
    except Exception:
        content = await page.content()
        print("⚠️ Page content (first 1000 chars):")
        print(content[:1000])
        raise Exception("CloakBrowser did not solve Turnstile. Try again or use 2Captcha.")

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

    # Matches: http://freeiptv.ottc.xyz:80/live/OLD_USER/OLD_PASS/file.ts
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