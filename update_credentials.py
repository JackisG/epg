#!/usr/bin/env python3
import os
import re
import sys
import requests
from bs4 import BeautifulSoup

OXYLABS_ENDPOINT = "https://realtime.oxylabs.io/v1/queries"
TARGET_URL = "https://freeiptv2023-d.ottc.xyz"
M3U_FILE = "languages/lit.m3u"


def fetch_credentials():
    payload = {
        "source": "universal",
        "url": TARGET_URL,
        "render": "html",
        "geo_location": "Lithuania",
    }

    resp = requests.post(
        OXYLABS_ENDPOINT,
        auth=(os.environ["OXYLABS_USERNAME"], os.environ["OXYLABS_PASSWORD"]),
        json=payload,
        timeout=120,
    )
    resp.raise_for_status()
    data = resp.json()

    # Extract rendered HTML from Oxylabs response
    html = None
    results = data.get("results", [])
    if results and "content" in results[0]:
        html = results[0]["content"]
    elif "content" in data:
        html = data["content"]
    else:
        raise RuntimeError(
            f"Unexpected Oxylabs response structure. Keys: {list(data.keys())}"
        )

    soup = BeautifulSoup(html, "html.parser")

    # Primary: read the input fields
    user_el = soup.find("input", {"id": "accUser"})
    pass_el = soup.find("input", {"id": "accPass"})
    username = user_el.get("value") if user_el else None
    password = pass_el.get("value") if pass_el else None

    # Fallback: parse username & password from the M3U link
    if not username or not password:
        m3u_el = soup.find("input", {"id": "m3uLink"})
        if m3u_el:
            m3u_url = m3u_el.get("value", "")
            m = re.search(r"username=([^&]+)&password=([^&]+)", m3u_url)
            if m:
                username, password = m.group(1), m.group(2)

    if not username or not password:
        # Save HTML for debugging if extraction fails
        with open("debug_page.html", "w", encoding="utf-8") as f:
            f.write(html)
        raise RuntimeError(
            "Failed to extract credentials. Saved debug_page.html for inspection."
        )

    return username.strip(), password.strip()


def update_m3u(new_user, new_pass):
    if not os.path.exists(M3U_FILE):
        raise FileNotFoundError(f"{M3U_FILE} not found in repo")

    with open(M3U_FILE, "r", encoding="utf-8") as f:
        content = f.read()

    original = content

    # Replace /live/USERNAME/PASSWORD/CHANNEL_ID.ts
    live_pattern = r"http://freeiptv\.ottc\.xyz:80/live/[^/]+/[^/]+/([^/\s]+\.ts)"
    content = re.sub(
        live_pattern,
        rf"http://freeiptv.ottc.xyz:80/live/{new_user}/{new_pass}/\1",
        content,
    )

    # Replace get.php links if any exist
    get_pattern = r"http://freeiptv\.ottc\.xyz:80/get\.php\?username=[^&]+&password=[^&]+"
    content = re.sub(
        get_pattern,
        f"http://freeiptv.ottc.xyz:80/get.php?username={new_user}&password={new_pass}",
        content,
    )

    changed = content != original
    if changed:
        with open(M3U_FILE, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"[OK] Updated {M3U_FILE} → {new_user} / {new_pass}")
    else:
        print("[INFO] No freeiptv links found or credentials already current.")

    return changed


def main():
    print("[INFO] Fetching credentials via Oxylabs...")
    new_user, new_pass = fetch_credentials()
    print(f"[INFO] Got username={new_user}, password={new_pass}")

    update_m3u(new_user, new_pass)
    sys.exit(0)


if __name__ == "__main__":
    main()