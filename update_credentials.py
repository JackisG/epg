#!/usr/bin/env python3
import os
import re
import sys
import time
import asyncio
import requests
from github import Github
from rebrowser_playwright.async_api import async_playwright

GITHUB_TOKEN = os.environ["GITHUB_TOKEN"]
ANTICAPTCHA_API_KEY = os.environ["ANTICAPTCHA_API_KEY"]
REPO_NAME = "JackisG/epg"
FILE_PATH = "languages/lit.m3u"
TARGET_URL = "https://freeiptv2023-d.ottc.xyz/index.php?action=view"

# Known sitekey for this domain (from earlier logs)
KNOWN_SITEKEY = "0x4AAAAAAA_Qtby-wpbozX7J"

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
    print("🌐 Launching rebrowser-playwright (stealth)...")
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

        # Apply stealth script
        await page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            delete window.__playwright__binding__;
            delete window.__pwInitScripts;
            window.chrome = { runtime: {} };
        """)

        print("🔗 Navigating to page...")
        await page.goto(TARGET_URL, wait_until="domcontentloaded", timeout=60000)

        # Wait for either credentials or the challenge
        try:
            await page.wait_for_selector("#accUser", timeout=15000)
            username = await page.get_attribute("#accUser", "value")
            password = await page.get_attribute("#accPass", "value")
            if username and password:
                print(f"👤 Credentials found! Username: {username}")
                print(f"🔑 Password: {password}")
                await browser.close()
                return username, password
        except Exception:
            print("⏳ Credentials not loaded yet. Looking for challenge...")

        # Extract sitekey from page, fallback to known one
        sitekey = None
        try:
            await page.wait_for_selector("[data-sitekey]", timeout=10000)
            sitekey = await page.get_attribute("[data-sitekey]", "data-sitekey")
        except Exception:
            pass

        if not sitekey:
            content = await page.content()
            match = re.search(r'data-sitekey=["\']([^"\']+)["\']', content)
            if match:
                sitekey = match.group(1)

        if not sitekey:
            print("⚠️ Could not find sitekey. Using known sitekey.")
            sitekey = KNOWN_SITEKEY

        print(f"🔑 Using sitekey: {sitekey}")

        # Solve via anti-captcha
        token = solve_turnstile_anticaptcha(sitekey, TARGET_URL)

        # Inject token and reload
        await page.evaluate(f"""
            const input = document.querySelector('input[name="cf-turnstile-response"]');
            if (input) input.value = '{token}';
        """)
        await page.wait_for_timeout(2000)
        await page.reload(wait_until="domcontentloaded")

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