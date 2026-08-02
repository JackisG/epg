#!/usr/bin/env python3
import os
import re
import sys
import time
import asyncio
import requests
from github import Github
from playwright.async_api import async_playwright

GITHUB_TOKEN = os.environ["GITHUB_TOKEN"]
CAPTCHA_API_KEY = os.environ["CAPTCHA_API_KEY"]
REPO_NAME = "JackisG/epg"
FILE_PATH = "languages/lit.m3u"
TARGET_URL = "https://freeiptv2023-d.ottc.xyz/index.php?action=view"

def solve_turnstile(sitekey, page_url):
    print("🧩 Submitting Turnstile to 2Captcha...")
    submit = requests.post(
        "https://2captcha.com/in.php",
        data={
            "key": CAPTCHA_API_KEY,
            "method": "turnstile",
            "sitekey": sitekey,
            "pageurl": page_url,
            "json": 1
        }
    )
    result = submit.json()
    if result["status"] != 1:
        raise Exception(f"Submission failed: {result}")
    
    captcha_id = result["request"]
    for _ in range(30):
        time.sleep(2)
        poll = requests.get(
            "https://2captcha.com/res.php",
            params={"key": CAPTCHA_API_KEY, "action": "get", "id": captcha_id, "json": 1}
        )
        data = poll.json()
        if data["status"] == 1:
            print("✅ Turnstile solved!")
            return data["request"]
        if data["request"] == "CAPCHA_NOT_READY":
            continue
        raise Exception(f"Solving failed: {data}")
    raise Exception("Timeout waiting for solution")

async def fetch_new_credentials():
    print("🌐 Launching browser...")
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox"])
        page = await browser.new_page()

        print("🔗 Navigating...")
        await page.goto(TARGET_URL, wait_until="domcontentloaded", timeout=30000)

        # Extract sitekey
        sitekey = await page.get_attribute("div.cf-turnstile", "data-sitekey")
        if not sitekey:
            content = await page.content()
            match = re.search(r'data-sitekey=["\']([^"\']+)["\']', content)
            sitekey = match.group(1) if match else None
        if not sitekey:
            raise Exception("Could not find Turnstile sitekey")
        print(f"🔑 Sitekey: {sitekey}")

        # Solve via API
        token = solve_turnstile(sitekey, TARGET_URL)

        # Inject token and reload
        await page.evaluate(f"""
            document.querySelector('input[name="cf-turnstile-response"]').value = '{token}';
        """)
        await page.wait_for_timeout(2000)
        await page.reload(wait_until="domcontentloaded")

        # Wait for credentials
        await page.wait_for_selector("#accUser", timeout=30000)
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

    # ✅ CORRECTED: matches path-based URLs like:
    # http://freeiptv.ottc.xyz:80/live/OLD_USER/OLD_PASS/47287.ts
    pattern = re.compile(
        r'(http://freeiptv\.ottc\.xyz:[0-9]+/live/)\d+(/\d+/[^/\s]+)'
    )

    for line in lines:
        m = pattern.search(line)
        if m:
            # Reconstruct: base_url + new_username + new_password + rest
            base = m.group(1)           # "http://freeiptv.ottc.xyz:80/live/"
            rest = m.group(2)           # "/OLD_PASS/47287.ts" (includes the trailing filename)
            new_line = line.replace(m.group(0), f"{base}{username}{rest}")
            new_lines.append(new_line)
            replaced += 1
            print(f"🔄 Updated: {line[:80]}...")
        else:
            new_lines.append(line)

    if replaced == 0:
        print("⚠️ No 'freeiptv.ottc.xyz' URLs found – nothing changed.")
        print("💡 Check that your lit.m3u contains URLs like: http://freeiptv.ottc.xyz:80/live/XXX/YYY/ZZZ.ts")
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