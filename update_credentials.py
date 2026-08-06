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


def fetch_solved_page():
    """
    First request: render the page and solve Turnstile.
    Return the HTML with the solved token and the cookies/headers for reuse.
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
    resp = requests.post(API_URL, json=payload, headers=headers, timeout=60)
    resp.raise_for_status()
    data = resp.json()
    results = data.get("results", [])
    if not results:
        raise RuntimeError(f"No results from Oxylabs: {data}")
    # Extract the content, cookies, and headers
    result = results[0]
    html = result.get("content")
    if not html:
        raise RuntimeError("No HTML content in Oxylabs response")
    # Get the cookies from the response (set-cookie header)
    cookies = {}
    for cookie in result.get("_response", {}).get("cookies", []):
        cookies[cookie["key"]] = cookie["value"]
    # Also get the request headers to reuse
    request_headers = result.get("_request", {}).get("headers", {})
    return html, cookies, request_headers


def extract_token_from_html(html):
    """Extract the cf-turnstile-response token from the hidden input."""
    soup = BeautifulSoup(html, "html.parser")
    token_input = soup.find("input", {"name": "cf-turnstile-response"})
    if token_input:
        token = token_input.get("value", "").strip()
        if token:
            return token
    raise RuntimeError("Could not extract Turnstile token from HTML")


def submit_token_and_get_credentials(token, cookies, headers):
    """
    Submit the token via POST request to get the credentials page.
    Reuse cookies and headers from the initial Oxylabs request.
    """
    session = requests.Session()
    session.headers.update({
        "User-Agent": headers.get("User-Agent", "Mozilla/5.0"),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": INDEX_URL,
        "Content-Type": "application/x-www-form-urlencoded",
        "Origin": BASE_URL,
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Cache-Control": "max-age=0",
    })
    session.cookies.update(cookies)
    data = {"cf-turnstile-response": token}
    # POST the token
    resp = session.post(INDEX_URL, data=data, allow_redirects=True, timeout=30)
    # The final URL should be /index.php?action=view
    if "IPTV account information" not in resp.text:
        # Maybe the redirect failed; try following manually
        if resp.status_code in (301, 302, 303, 307, 308):
            location = resp.headers.get("Location")
            if location:
                if not location.startswith(("http://", "https://")):
                    location = urljoin(BASE_URL, location)
                resp = session.get(location, allow_redirects=True, timeout=30)
        # Check again
        if "IPTV account information" not in resp.text:
            snippet = resp.text[:500]
            raise RuntimeError(f"Credentials page not reached. Snippet: {snippet}")
    return resp.text


def parse_credentials(html):
    soup = BeautifulSoup(html, "html.parser")
    user_input = soup.find("input", {"id": "accUser"})
    pass_input = soup.find("input", {"id": "accPass"})
    if not user_input or not pass_input:
        raise RuntimeError("Credentials fields not found")
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
    print("Step 1: Solving captcha via Oxylabs...")
    html, cookies, headers = fetch_solved_page()
    token = extract_token_from_html(html)
    print(f"Token extracted: {token[:30]}...")

    print("Step 2: Submitting token to get credentials...")
    credentials_html = submit_token_and_get_credentials(token, cookies, headers)

    username, password = parse_credentials(credentials_html)
    print(f"New credentials: {username} / {password}")

    m3u_path = "languages/lit.m3u"
    if not os.path.isfile(m3u_path):
        raise FileNotFoundError(f"{m3u_path} not found")
    update_m3u_file(m3u_path, username, password)


if __name__ == "__main__":
    main()