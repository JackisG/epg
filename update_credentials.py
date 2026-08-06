import os
import re
import base64
import json
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin

OXYLABS_USERNAME = os.environ.get("OXYLABS_USERNAME")
OXYLABS_PASSWORD = os.environ.get("OXYLABS_PASSWORD")
if not OXYLABS_USERNAME or not OXYLABS_PASSWORD:
    raise RuntimeError("Oxylabs credentials not set")

BASE_URL = "https://freeiptv2023-d.ottc.xyz"
INDEX_URL = f"{BASE_URL}/index.php"
API_URL = "https://realtime.oxylabs.io/v1/queries"
AUTH_HEADER = base64.b64encode(f"{OXYLABS_USERNAME}:{OXYLABS_PASSWORD}".encode()).decode()


def get_solved_captcha_data():
    """
    Use Oxylabs to render the page and solve the Turnstile.
    Returns the HTML with the solved token and the session cookie.
    """
    payload = {
        "source": "universal",
        "url": INDEX_URL,
        "render": "html",
        "captcha": {"solve": True},
        "wait_for_selector": "#create-btn:not([disabled])",
        "wait_for_timeout": 30000
    }
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Basic {AUTH_HEADER}"
    }
    print("Submitting captcha request to Oxylabs...")
    resp = requests.post(API_URL, json=payload, headers=headers, timeout=60)
    resp.raise_for_status()
    data = resp.json()
    if data.get("status") != "done":
        raise RuntimeError(f"Oxylabs job failed: {data}")
    results = data.get("results", [])
    if not results:
        raise RuntimeError("No results in Oxylabs response")
    html = results[0].get("content")
    if not html:
        raise RuntimeError("No HTML content in Oxylabs response")
    # Extract the session cookie
    cookies = {}
    for cookie in results[0].get("_response", {}).get("cookies", []):
        cookies[cookie["key"]] = cookie["value"]
    print("Captcha solved, token and cookie retrieved.")
    return html, cookies


def extract_token(html):
    soup = BeautifulSoup(html, "html.parser")
    token_input = soup.find("input", {"name": "cf-turnstile-response"})
    if token_input:
        token = token_input.get("value", "").strip()
        if token:
            return token
    raise RuntimeError("Could not extract Turnstile token from HTML")


def submit_token_and_get_credentials(token, cookies):
    """
    Submit the token via POST using the Oxylabs cookie to obtain the credentials page.
    """
    session = requests.Session()
    session.cookies.update(cookies)
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": INDEX_URL,
        "Content-Type": "application/x-www-form-urlencoded",
        "Origin": BASE_URL,
        "Upgrade-Insecure-Requests": "1",
        "Cache-Control": "max-age=0",
    })
    data = {"cf-turnstile-response": token}
    print("Submitting token to get credentials...")
    resp = session.post(INDEX_URL, data=data, allow_redirects=True, timeout=30)
    # If not redirected, try the redirect manually
    if "IPTV account information" not in resp.text:
        if resp.status_code in (301, 302, 303, 307, 308):
            location = resp.headers.get("Location")
            if location:
                if not location.startswith(("http://", "https://")):
                    location = urljoin(BASE_URL, location)
                resp = session.get(location, allow_redirects=True, timeout=30)
    if "IPTV account information" not in resp.text:
        snippet = resp.text[:500]
        raise RuntimeError(f"Credentials page not reached. Snippet: {snippet}")
    return resp.text


def parse_credentials(html):
    soup = BeautifulSoup(html, "html.parser")
    user_input = soup.find("input", {"id": "accUser"})
    pass_input = soup.find("input", {"id": "accPass"})
    if not user_input or not pass_input:
        raise RuntimeError("Credentials fields not found in final page")
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
    # Step 1: Get solved captcha page (with token and cookie)
    html, cookies = get_solved_captcha_data()
    token = extract_token(html)
    print(f"Token extracted: {token[:30]}...")

    # Step 2: Submit token manually using the same cookie
    credentials_html = submit_token_and_get_credentials(token, cookies)

    # Step 3: Parse credentials
    username, password = parse_credentials(credentials_html)
    print(f"✅ New credentials: {username} / {password}")

    # Step 4: Update M3U file
    m3u_path = "languages/lit.m3u"
    if not os.path.isfile(m3u_path):
        raise FileNotFoundError(f"{m3u_path} not found")
    update_m3u_file(m3u_path, username, password)


if __name__ == "__main__":
    main()