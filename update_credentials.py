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
ANTICAPTCHA_API_KEY = os.environ["ANTICAPTCHA_API_KEY"]
REPO_NAME = "JackisG/epg"
FILE_PATH = "languages/lit.m3u"
TARGET_URL = "https://freeiptv2023-d.ottc.xyz/index.php?action=view"

def solve_turnstile_anticaptcha(sitekey, page_url):
    print("🧩 Submitting Turnstile to anti-captcha.com...")
    create_payload = {
        "clientKey": ANTICAPTCHA_API_KEY,
        "task": {
            "type": "TurnstileTaskProxyless",
            "websiteURL": page_url,
            "websiteKey": sitekey,
        }
    }
    create_resp = requests.post(
        "https://api.anti-captcha.com/createTask",
        json=create_payload,
        timeout=30
    )
    create_data = create_resp.json()
    if create_data.get("errorId") != 0:
        raise Exception(f"Create task failed: {create_data}")
    task_id = create_data["taskId"]
    print(f"📝 Task created, ID: {task_id}")

    result_payload = {"clientKey": ANTICAPTCHA_API_KEY, "taskId": task_id}
    for _ in range(30):
        time.sleep(3)
        result_resp = requests.post(
            "https://api.anti-captcha.com/getTaskResult",
            json=result_payload,
            timeout=30
        )
        result_data = result_resp.json()
        if result_data.get("errorId") != 0:
            raise Exception(f"Polling error: {result_data}")
        if result_data.get("status") == "ready":
            token = result_data["solution"]["token"]
            print("✅ Turnstile solved!")
            return token
    raise Exception("Timeout waiting for solution")

async def fetch_new_credentials():
    print("🌐 Launching browser with networkidle...")
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox"])
        page = await browser.new_page()

        print("🔗 Navigating to page (wait until network idle)...")
        try:
            await page.goto(TARGET_URL, wait_until="networkidle", timeout=60000)
        except Exception:
            # Even if timeout, we might still have the page partially loaded
            pass

        # Wait a bit for dynamic content
        await page.wait_for_timeout(5000)

        # Try to find the Turnstile widget by data-sitekey attribute
        sitekey = None
        try:
            # Wait for any element with data-sitekey
            await page.wait_for_selector("[data-sitekey]", timeout=30000)
            sitekey = await page.get_attribute("[data-sitekey]", "data-sitekey")
        except Exception:
            # Fallback: search in raw HTML
            content = await page.content()
            match = re.search(r'data-sitekey=["\']([^"\']+)["\']', content)
            if match:
                sitekey = match.group(1)

        if not sitekey:
            # Dump full HTML for debugging
            content = await page.content()
            print("⚠️ Full page content (first 2000 chars):")
            print(content[:2000])
            raise Exception("Could not find Turnstile sitekey. Page may be blocked or using a different challenge.")

        print(f"🔑 Sitekey: {sitekey}")

        # Solve via anti-captcha
        token = solve_turnstile_anticaptcha(sitekey, TARGET_URL)

        # Inject token
        await page.evaluate(f"""
            const input = document.querySelector('input[name="cf-turnstile-response"]');
            if (input) input.value = '{token}';
        """)
        await page.wait_for_timeout(2000)
        await page.reload(wait_until="networkidle")

        # Wait for credentials
        try:
            await page.wait_for_selector("#accUser", timeout=30000)
        except Exception:
            content = await page.content()
            print("⚠️ Page after injection (first 1000 chars):")
            print(content[:1000])
            raise Exception("Credentials not found – token may have been rejected.")

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