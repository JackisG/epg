import os
import re
import time
import random
import string
import requests
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright
from playwright_stealth import stealth_sync

BASE_URL = "https://freeiptv2023-d.ottc.xyz"
TWO_CAPTCHA_API_KEY = os.environ.get("TWO_CAPTCHA_API_KEY")
if not TWO_CAPTCHA_API_KEY:
    raise RuntimeError("TWO_CAPTCHA_API_KEY not set")

SITEKEY = "0x4AAAAAAA_Qtby-wpbozX7J"


def solve_turnstile(page_url: str, action: str = "submit", cdata: str = None) -> str:
    """Solve Turnstile using 2Captcha API with optional action and cdata."""
    if cdata is None:
        cdata = ''.join(random.choices(string.ascii_letters + string.digits, k=12))
    create_url = "https://2captcha.com/in.php"
    data = {
        "key": TWO_CAPTCHA_API_KEY,
        "method": "turnstile",
        "sitekey": SITEKEY,
        "pageurl": page_url,
        "json": 1,
        "action": action,
        "data": cdata,
    }
    resp = requests.post(create_url, data=data)
    resp_json = resp.json()
    if resp_json.get("status") != 1:
        raise RuntimeError(f"Failed to create captcha task: {resp_json}")
    captcha_id = resp_json["request"]
    print(f"Captcha created with ID: {captcha_id} (action={action}, cdata={cdata})")

    result_url = "https://2captcha.com/res.php"
    poll_data = {
        "key": TWO_CAPTCHA_API_KEY,
        "action": "get",
        "id": captcha_id,
        "json": 1,
    }
    max_wait = 120
    start = time.time()
    while time.time() - start < max_wait:
        poll_resp = requests.get(result_url, params=poll_data)
        poll_json = poll_resp.json()
        if poll_json.get("status") == 1:
            token = poll_json.get("request")
            if token:
                return token
        elif poll_json.get("request") == "CAPCHA_NOT_READY":
            time.sleep(3)
            continue
        else:
            raise RuntimeError(f"Error solving captcha: {poll_json}")
    raise RuntimeError("Timed out waiting for captcha solution")


def fetch_credentials(max_retries=3) -> tuple[str, str]:
    for attempt in range(max_retries):
        print(f"\nAttempt {attempt+1}/{max_retries}")
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
            page = context.new_page()
            stealth_sync(page)

            # Go to the page
            page.goto(BASE_URL + "/index.php")
            page.wait_for_load_state("networkidle")

            # Solve the challenge (try different action/cdata combinations)
            action = "submit" if attempt % 2 == 0 else "login"
            cdata = ''.join(random.choices(string.ascii_letters + string.digits, k=12))
            token = solve_turnstile(BASE_URL + "/index.php", action=action, cdata=cdata)
            print(f"Token: {token[:30]}...")

            # Set the token and enable the button
            page.evaluate(f"""
                document.querySelector("input[name='cf-turnstile-response']").value = "{token}";
                document.querySelector("#create-btn").disabled = false;
                document.querySelector("#please-wait").style.display = "none";
            """)

            # Submit the form
            page.click("input[type='submit']")

            # Wait for the credentials page
            try:
                page.wait_for_url("**/index.php?action=view", timeout=15000)
            except:
                page.wait_for_load_state("networkidle", timeout=5000)
            time.sleep(2)

            # Check if we got the credentials page
            if "IPTV account information" in page.content():
                # Success
                break
            else:
                print("Token rejected, retrying...")
                # Log a snippet for debugging
                snippet = page.content()[:500]
                print("Snippet:", snippet)
                browser.close()
                if attempt == max_retries - 1:
                    raise RuntimeError("Failed to reach credentials page after multiple attempts")
                continue

        # If we break out, we have success
        html = page.content()
        soup = BeautifulSoup(html, "html.parser")
        user_input = soup.find("input", {"id": "accUser"})
        pass_input = soup.find("input", {"id": "accPass"})
        if not user_input or not pass_input:
            raise RuntimeError("Credentials not found on page")
        username = user_input.get("value", "").strip()
        password = pass_input.get("value", "").strip()
        if not username or not password:
            raise RuntimeError("Empty credentials")
        print(f"New credentials: {username} / {password}")
        browser.close()
        return username, password


def update_m3u(file_path: str, new_user: str, new_pass: str) -> None:
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    pattern = r"http://freeiptv\.ottc\.xyz:80/live/(\d+)/(\d+)/"
    matches = re.findall(pattern, content)
    if not matches:
        raise RuntimeError("No existing credentials found in lit.m3u")
    old_user, old_pass = matches[0]
    print(f"Old credentials: {old_user} / {old_pass}")

    new_content = re.sub(
        pattern,
        f"http://freeiptv.ottc.xyz:80/live/{new_user}/{new_pass}/",
        content,
    )
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(new_content)
    print("lit.m3u updated.")


def main():
    user, passw = fetch_credentials()
    m3u_path = "languages/lit.m3u"
    if not os.path.isfile(m3u_path):
        raise FileNotFoundError(m3u_path)
    update_m3u(m3u_path, user, passw)


if __name__ == "__main__":
    main()