import os
import re
import time
import base64
import json
import requests
from bs4 import BeautifulSoup

# Oxylabs credentials from GitHub Secrets
OXYLABS_USERNAME = os.environ.get("OXYLABS_USERNAME")
OXYLABS_PASSWORD = os.environ.get("OXYLABS_PASSWORD")
if not OXYLABS_USERNAME or not OXYLABS_PASSWORD:
    raise RuntimeError("Oxylabs credentials not set in environment")

BASE_URL = "https://freeiptv2023-d.ottc.xyz"
INDEX_URL = f"{BASE_URL}/index.php"

# Oxylabs API endpoint
API_URL = "https://realtime.oxylabs.io/v1/queries"

# Basic Auth header
auth_header = base64.b64encode(f"{OXYLABS_USERNAME}:{OXYLABS_PASSWORD}".encode()).decode()

def fetch_credentials_via_oxylabs():
    """
    Use Oxylabs Web Scraper API to:
    1. Navigate to index.php
    2. Solve Cloudflare Turnstile
    3. Click the submit button
    4. Wait for the credentials page to load
    5. Return the final HTML content
    """
    # Payload for Oxylabs
    payload = {
        "source": "universal",
        "url": INDEX_URL,
        "render": "html",          # JavaScript rendering
        "captcha": {
            "solve": True          # automatically solve Turnstile
        },
        "actions": [
            {
                "type": "click",
                "selector": "#create-btn",
                "timeout": 10000   # wait up to 10s for button to be enabled
            }
        ],
        "wait_for": {
            "selector": "#accUser",  # wait for credentials field to appear
            "timeout": 15000
        }
    }

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Basic {auth_header}"
    }

    # Send request to Oxylabs
    response = requests.post(API_URL, json=payload, headers=headers, timeout=60)
    response.raise_for_status()

    data = response.json()
    # Check for successful response
    if data.get("status") != "done":
        raise RuntimeError(f"Oxylabs request failed: {data}")

    # Extract HTML from the results
    results = data.get("results", [])
    if not results:
        raise RuntimeError("No results from Oxylabs")
    html = results[0].get("content")
    if not html:
        raise RuntimeError("No HTML content in Oxylabs response")

    return html


def parse_credentials(html):
    """Extract username and password from the credentials page HTML."""
    soup = BeautifulSoup(html, "html.parser")
    user_input = soup.find("input", {"id": "accUser"})
    pass_input = soup.find("input", {"id": "accPass"})
    if not user_input or not pass_input:
        raise RuntimeError("Credentials fields not found in page")
    username = user_input.get("value", "").strip()
    password = pass_input.get("value", "").strip()
    if not username or not password:
        raise RuntimeError("Empty credentials")
    return username, password


def update_m3u_file(file_path, new_user, new_pass):
    """Replace old credentials in the M3U file with new ones."""
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Find existing credentials from any URL pattern
    pattern = r"http://freeiptv\.ottc\.xyz:80/live/(\d+)/(\d+)/"
    matches = re.findall(pattern, content)
    if not matches:
        raise RuntimeError("No existing credentials found in lit.m3u")
    old_user, old_pass = matches[0]
    print(f"Old credentials: {old_user} / {old_pass}")

    new_content = re.sub(
        pattern,
        f"http://freeiptv.ottc.xyz:80/live/{new_user}/{new_pass}/",
        content
    )
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(new_content)
    print("lit.m3u updated successfully.")


def main():
    print("Fetching credentials via Oxylabs...")
    html = fetch_credentials_via_oxylabs()
    username, password = parse_credentials(html)
    print(f"New credentials: {username} / {password}")

    m3u_path = "languages/lit.m3u"
    if not os.path.isfile(m3u_path):
        raise FileNotFoundError(f"{m3u_path} not found")
    update_m3u_file(m3u_path, username, password)


if __name__ == "__main__":
    main()
