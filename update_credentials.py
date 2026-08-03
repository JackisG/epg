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
TWOCAPTCHA_API_KEY = os.environ["TWOCAPTCHA_API_KEY"]
REPO_NAME = "JackisG/epg"
FILE_PATH = "languages/lit.m3u"
TARGET_URL = "https://freeiptv2023-d.ottc.xyz/index.php?action=view"

def solve_turnstile_2captcha(sitekey, page_url):
    print(f"🧩 Submitting Turnstile to 2Captcha (sitekey: {sitekey})...")
    submit_payload = {
        "key": TWOCAPTCHA_API_KEY,
        "method": "turnstile",
        "sitekey": sitekey,
        "pageurl": page_url,
        "json": 1,
    }
    submit_resp = requests.post("https://2captcha.com/in.php", data=submit_payload, timeout=30)
    submit_data = submit_resp.json()
    if submit_data.get("status") != 1:
        raise Exception(f"Submission failed: {submit_data}")
    captcha_id = submit_data["request"]
    print(f"📝 Captcha ID: {captcha_id}")

    result_payload = {"key": TWOCAPTCHA_API_KEY, "action": "get", "id": captcha_id, "json": 1}
    for _ in range(30):
        time.sleep(3)
        result_resp = requests.get("https://2captcha.com/res.php", params=result_payload, timeout=30)
        result_data = result_resp.json()
        if result_data.get("status") == 1:
            token = result_data["request"]
            print("✅ Turnstile solved!")
            return token
        if result_data.get("request") == "CAPCHA_NOT_READY":
            continue
        raise Exception(f"Polling error: {result_data}")
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

        await page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            delete window.__playwright__binding__;
            delete window.__pwInitScripts;
            window.chrome = { runtime: {} };
        """)

        print("🔗 Navigating to page...")
        await page.goto(TARGET_URL, wait_until="domcontentloaded", timeout=60000)

        # Wait for the page to settle and maybe load the challenge
        await page.wait_for_timeout(5000)

        # Check if credentials already visible
        try:
            await page.wait_for_selector("#accUser", timeout=10000)
            username = await page.get_attribute("#accUser", "value")
            password = await page.get_attribute("#accPass", "value")
            if username and password:
                print(f"👤 Credentials found! Username: {username}")
                await browser.close()
                return username, password
        except Exception:
            pass

        # Extract sitekey - wait longer and try multiple selectors
        sitekey = None
        for attempt in range(3):  # retry up to 3 times
            try:
                # Try to find the Turnstile widget
                await page.wait_for_selector("[data-sitekey]", timeout=15000)
                sitekey = await page.get_attribute("[data-sitekey]", "data-sitekey")
                if sitekey:
                    break
            except Exception:
                # Maybe the widget is inside an iframe; try to get from page source
                content = await page.content()
                match = re.search(r'data-sitekey=["\']([^"\']+)["\']', content)
                if match:
                    sitekey = match.group(1)
                    break
            await page.wait_for_timeout(3000)

        if not sitekey:
            # Last resort: use a known sitekey from previous runs (might be stale)
            print("⚠️ Could not find sitekey. Using known sitekey (may be outdated).")
            sitekey = "0x4AAAAAAA_Qtby-wpbozX7J"

        print(f"🔑 Using sitekey: {sitekey}")

        # Solve via 2Captcha
        token = solve_turnstile_2captcha(sitekey, TARGET_URL)

        # Inject token
        await page.evaluate(f"""
            const input = document.querySelector('input[name="cf-turnstile-response"]');
            if (input) input.value = '{token}';
            // Also try to trigger the submit event
            const form = input ? input.closest('form') : null;
            if (form) {
                form.dispatchEvent(new Event('submit', { bubbles: true }));
            }
        """)

        # Wait for the challenge to disappear and credentials to appear
        try:
            # Wait for the Turnstile widget to disappear (or credentials to appear)
            await page.wait_for_selector("#accUser", timeout=60000)
        except Exception:
            content = await page.content()
            print("⚠️ Page after injection (full content):")
            print(content[:2000])
            # Also check for any error messages
            if "The security check didn't complete successfully" in content:
                raise Exception("Token rejected by Cloudflare")
            raise Exception("Credentials not found after injection")

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