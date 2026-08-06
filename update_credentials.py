#!/usr/bin/env python3
import re
import os
import sys
import requests
from bs4 import BeautifulSoup
from datetime import datetime
import pytz


def get_credentials():
    """
    Uses Oxylabs Browser source to load the target page, click the invisible
    captcha button, and extract the displayed username and password.
    """
    oxy_user = os.environ["OXYLABS_USERNAME"]
    oxy_pass = os.environ["OXYLABS_PASSWORD"]

    payload = {
        "source": "browser",
        "url": "https://freeiptv2023-d.ottc.xyz",
        "browser_instructions": [
            {"type": "wait", "timeout": 5},
            # Click the button that triggers the invisible captcha.
            # Adjust the CSS selector if the button doesn't match.
            {"type": "click", "selector": "button"},
            {"type": "wait", "timeout": 5},
        ],
    }

    resp = requests.post(
        "https://realtime.oxylabs.io/v1/queries",
        auth=(oxy_user, oxy_pass),
        json=payload,
        timeout=120,
    )
    resp.raise_for_status()
    data = resp.json()

    # Extract the final HTML from the response
    try:
        html = data["results"][0]["content"]
    except (KeyError, IndexError):
        raise Exception("Failed to obtain page content from Oxylabs response.")

    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text()

    # First, look for labelled "Username" / "Password"
    user_match = re.search(r"Username\s*[:\s]*(\d+)", text, re.IGNORECASE)
    pass_match = re.search(r"Password\s*[:\s]*(\d+)", text, re.IGNORECASE)

    if user_match and pass_match:
        username = user_match.group(1)
        password = pass_match.group(1)
    else:
        # Fallback: find the first two 12‑digit numbers (typical length)
        numbers = re.findall(r"\b\d{12}\b", text)
        if len(numbers) >= 2:
            username = numbers[0]
            password = numbers[1]
        else:
            raise Exception("Could not parse username/password from the page.")

    print(f"New credentials: username = {username}, password = {password}")
    return username, password


def update_m3u_file(username, password):
    """Replace all occurrences of old credentials in lit.m3u with the new ones."""
    filepath = "languages/lit.m3u"
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    # Matches URLs like http://freeiptv.ottc.xyz:80/live/USER/PASS/stream.ts
    pattern = r"(http://freeiptv\.ottc\.xyz:80/live/)(\d+)(/)(\d+)(/\d+\.ts)"
    new_content = re.sub(pattern, rf"\1{username}\3{password}\5", content)

    if new_content == content:
        print("Credentials unchanged – nothing to commit.")
        sys.exit(0)

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(new_content)
    print("lit.m3u updated successfully.")


def main():
    # Only run at exactly 05:00 Vilnius time (handles DST)
    tz = pytz.timezone("Europe/Vilnius")
    now = datetime.now(tz)
    if now.hour != 5:
        print(f"Current Vilnius time is {now.hour}:{now.minute}, not 5:00 – exiting.")
        sys.exit(0)

    user, pwd = get_credentials()
    update_m3u_file(user, pwd)


if __name__ == "__main__":
    main()