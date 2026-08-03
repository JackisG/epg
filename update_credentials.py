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


def solve_turnstile(page_url: str, action: str = None, cdata: str = None, method: str = "turnstile") -> str:
    """Solve Turnstile with optional action and cdata."""
    create_url = "https://2captcha.com/in.php"
    data = {
        "key": TWO_CAPTCHA_API_KEY,
        "method": method,
        "sitekey": SITEKEY,
        "pageurl": page_url,
        "json": 1,
    }
    if action:
        data["action"] = action
    if cdata:
        data["data"] = cdata
    resp = requests.post(create_url, data=data)
    resp_json = resp.json()
    if resp_json.get("status") != 1:
        raise RuntimeError(f"Failed to create captcha task: {resp_json}")
    captcha_id = resp_json["request"]
    print(f"Captcha ID: {captcha_id} (method={method}, action={action}, cdata={cdata})")

    result_url = "https://2captcha.com/res.php"
    poll_data = {
        "key": TWO_CAPTCHA_API_KEY,
        "action": "get",
        "id": captcha_id,
        "json": 1,
    }
    max_wait = 180
    start = time.time()
    while time.time() - start < max_wait:
        poll_resp = requests.get(result_url, params=poll_data)
        poll_json = poll_resp.json()
        if poll_json.get("status") == 1:
            token = poll_json.get("request")
            if token:
                return token
        elif poll_json.get("request") == "CAPCHA_NOT_READY":
            time.sleep(4)
            continue
        else:
            raise RuntimeError(f"Error solving captcha: {poll_json}")
    raise RuntimeError("Timed out waiting for captcha solution")


def fetch_credentials(max_retries=5) -> tuple[str, str]:
    attempts = 0
    # List of combinations to try
    combos = [
        {"method": "turnstile", "action": None, "cdata": None},
        {"method": "turnstile", "action": "submit", "cdata": ''.join(random.choices(string.ascii_letters + string.digits, k=12))},
        {"method": "turnstile", "action": "login", "cdata": ''.join(random.choices(string.ascii_letters + string.digits, k=12))},
        {"method": "turnstile_managed", "action": None, "cdata": None},
    ]
    while attempts < max_retries:
        combo = combos[attempts % len(combos)]
        print(f"\nAttempt {attempts+1}/{max_retries} with {combo}")
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                locale="en-US",
                timezone_id="Europe/Vilnius"
            )
            page = context.new_page()
            stealth_sync(page)

            # Go to page
            page.goto(BASE_URL + "/index.php")
            page.wait_for_load_state("networkidle")

            # Solve captcha with this combo
            token = solve_turnstile(
                BASE_URL + "/index.php",
                action=combo["action"],
                cdata=combo["cdata"],
                method=combo["method"]
            )
            print(f"Token: {token[:30]}...")

            # Inject token and enable button
            page.evaluate(f"""
                document.querySelector("input[name='cf-turnstile-response']").value = "{token}";
                document.querySelector("#create-btn").disabled = false;
                document.querySelector("#please-wait").style.display = "none";
            """)

            # Submit
            page.click("input[type='submit']")
            try:
                page.wait_for_url("**/index.php?action=view", timeout=15000)
            except:
                page.wait_for_load_state("networkidle", timeout=5000)
            time.sleep(2)

            # Check success
            content = page.content()
            if "IPTV account information" in content:
                # success
                break
            else:
                print("Token rejected, retrying...")
                snippet = content[:500]
                print("Snippet:", snippet)
                browser.close()
                attempts += 1
                continue

        if attempts >= max_retries:
            raise RuntimeError("All attempts failed")

    # Extract credentials (success case)
    html = page.content()
    soup = BeautifulSoup(html, "html.parser")
    user_input = soup.find("input", {"id": "accUser"})
    pass_input = soup.find("input", {"id": "accPass"})
    if not user_input or not pass_input:
        raise RuntimeError("Credentials not found")
    username = user_input.get("value", "").strip()
    password = pass_input.get("value", "").strip()
    if not username or not password:
        raise RuntimeError("Empty credentials")
    print(f"Success: {username} / {password}")
    browser.close()
    return username, password


def update_m3u(file_path: str, new_user: str, new_pass: str) -> None:
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()
    pattern = r"http://freeiptv\.ottc\.xyz:80/live/(\d+)/(\d+)/"
    matches = re.findall(pattern, content)
    if not matches:
        raise RuntimeError("No existing credentials found")
    old_user, old_pass = matches[0]
    print(f"Old: {old_user} / {old_pass}")
    new_content = re.sub(pattern, f"http://freeiptv.ottc.xyz:80/live/{new_user}/{new_pass}/", content)
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