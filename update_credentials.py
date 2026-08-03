#!/usr/bin/env python3
import os
import re
import sys
import time
import asyncio
import requests
from github import Github
from cloakbrowser import launch_async

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
    print("🌐 Launching CloakBrowser Pro (with xvfb)...")
    browser = await launch_async(
        headless=False,
        humanize=True,
        args=["--no-sandbox", "--disable-dev-shm-usage"],
        timeout=120000,
    )
    page = await browser.new_page()

    print("🔗 Navigating to page (domcontentloaded)...")
    await page.goto(TARGET_URL, wait_until="domcontentloaded", timeout=60000)

    # Wait for either the challenge or the credentials
    # Let CloakBrowser try to solve automatically for a while
    await page.wait_for_timeout(10000)

    # Check if credentials already loaded (Turnstile solved by CloakBrowser)
    username = await page.get_attribute("#accUser", "value")
    password = await page.get_attribute("#accPass", "value")
    if username and password:
        print(f"👤 CloakBrowser auto-solved! Username: {username}")
        print(f"🔑 Password: {password}")
        await browser.close()
        return username, password

    # If not, manually solve via anti-captcha
    print("⏳ Turnstile not auto-solved. Extracting sitekey for manual solve...")
    sitekey = None
    try:
        # Wait for the Turnstile iframe to appear
        await page.wait_for_selector("[data-sitekey]", timeout=30000)
        sitekey = await page.get_attribute("[data-sitekey]", "data-sitekey")
    except Exception:
        content = await page.content()
        match = re.search(r'data-sitekey=["\']([^"\']+)["\']', content)
        if match:
            sitekey = match.group(1)

    if not sitekey:
        content = await page.content()
        print("⚠️ Full page content (first 2000 chars):")
        print(content[:2000])
        raise Exception("Could not find Turnstile sitekey. Page may be blocking.")

    print(f"🔑 Sitekey: {sitekey}")

    # Solve via anti-captcha
    token = solve_turnstile_anticaptcha(sitekey, TARGET_URL)

    # Inject token
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

# update_m3u_file and main are unchanged (same as previous version)