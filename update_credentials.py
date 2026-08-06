import os
import re
import base64
import json
import requests
from bs4 import BeautifulSoup

OXYLABS_USERNAME = os.environ.get("OXYLABS_USERNAME")
OXYLABS_PASSWORD = os.environ.get("OXYLABS_PASSWORD")
if not OXYLABS_USERNAME or not OXYLABS_PASSWORD:
    raise RuntimeError("Oxylabs credentials not set")

BASE_URL = "https://freeiptv2023-d.ottc.xyz"
INDEX_URL = f"{BASE_URL}/index.php"
API_URL = "https://realtime.oxylabs.io/v1/queries"
AUTH_HEADER = base64.b64encode(f"{OXYLABS_USERNAME}:{OXYLABS_PASSWORD}".encode()).decode()


def fetch_credentials_via_oxylabs():
    """
    Use Oxylabs to solve Turnstile, click the submit button,
    and wait for the credentials page. Returns the final HTML.
    """
    payload = {
        "source": "universal",
        "url": INDEX_URL,
        "render": "html",
        "captcha": {"solve": True},
        "follow_redirects": True,
        "actions": [
            # Wait for the button to become enabled (captcha solved)
            {
                "type": "wait_for",
                "selector": "#create-btn:not([disabled])",
                "timeout": 30000
            },
            # Click the button
            {
                "type": "click",
                "selector": "#create-btn"
            }
        ],
        # Wait for the credentials page to load (presence of #accUser)
        "wait_for_selector": "#accUser",
        "wait_for_timeout": 15000
    }

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Basic {AUTH_HEADER}"
    }

    print("Submitting request to Oxylabs...")
    response = requests.post(API_URL, json=payload, headers=headers, timeout=60)
    response.raise_for_status()

    data = response.json()
    print(f"Oxylabs job status: {data.get('status')}")

    # Save full response for debugging (truncated)
    full_response = json.dumps(data, indent=2)
    if len(full_response) > 2000:
        print("Full response (first 2000 chars):")
        print(full_response[:2000] + "...")
    else:
        print("Full response:")
        print(full_response)

    if data.get("status") != "done":
        raise RuntimeError(f"Oxylabs job failed: {data}")

    results = data.get("results", [])
    if not results:
        raise RuntimeError("No results in Oxylabs response")

    html = results[0].get("content")
    if not html:
        raise RuntimeError("No HTML content in Oxylabs response")

    # Log a snippet of the final HTML
    print("Final HTML snippet (first 500 chars):")
    print(html[:500] + "...")
    return html


def parse_credentials(html):
    soup = BeautifulSoup(html, "html.parser")
    user_input = soup.find("input", {"id": "accUser"})
    pass_input = soup.find("input", {"id": "accPass"})
    if not user_input or not pass_input:
        raise RuntimeError("Credentials fields not found in the final HTML")
    username = user_input.get("value", "").strip()
    password = pass_input.get("value", "").strip()
    if not username or not password:
        raise RuntimeError("Empty credentials")
    return username, password


def update_m3u_file(file_path, new_user, new_pass):
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()
    pattern = r"http://freeiptv\.ottc\.xyz:80/live/(\d+)/(\d+)/"
    matches = re.findall(pattern, content)
    if not matches:
        raise RuntimeError("No existing credentials found in lit.m3u")
    old_user, old_pass = matches[0]
    print(f"Old credentials: {old_user} / {old_pass}")
    new_content = re.sub(pattern, f"http://freeiptv.ottc.xyz:80/live/{new_user}/{new_pass}/", content)
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(new_content)
    print("lit.m3u updated successfully.")


def main():
    print("Fetching credentials via Oxylabs (full automation)...")
    html = fetch_credentials_via_oxylabs()

    username, password = parse_credentials(html)
    print(f"✅ New credentials: {username} / {password}")

    m3u_path = "languages/lit.m3u"
    if not os.path.isfile(m3u_path):
        raise FileNotFoundError(f"{m3u_path} not found")
    update_m3u_file(m3u_path, username, password)


if __name__ == "__main__":
    main()