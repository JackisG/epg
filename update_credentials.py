import os
import re
import time
import requests
from bs4 import BeautifulSoup
from twocaptcha import TwoCaptcha

BASE_URL = "https://freeiptv2023-d.ottc.xyz"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
TWO_CAPTCHA_API_KEY = os.environ.get("TWO_CAPTCHA_API_KEY")

if not TWO_CAPTCHA_API_KEY:
    raise RuntimeError("TWO_CAPTCHA_API_KEY environment variable not set")


def solve_turnstile(sitekey: str, page_url: str) -> str:
    """Solve Cloudflare Turnstile using 2Captcha and return the token."""
    solver = TwoCaptcha(TWO_CAPTCHA_API_KEY)
    try:
        result = solver.turnstile(sitekey=sitekey, url=page_url)
        return result["code"]
    except Exception as e:
        print(f"2Captcha error: {e}")
        raise


def follow_redirects(session, response, max_redirects=10):
    """Manually follow redirects until a non-redirect response is received."""
    redirect_count = 0
    while response.status_code in (301, 302, 303, 307, 308) and redirect_count < max_redirects:
        location = response.headers.get("Location")
        if not location:
            break
        if not location.startswith(("http://", "https://")):
            location = requests.compat.urljoin(BASE_URL, location)
        print(f"Following redirect to {location}")
        response = session.get(location, allow_redirects=False)
        redirect_count += 1
    return response


def fetch_credentials() -> tuple[str, str]:
    """Fetch new username and password from the website."""
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})

    # 1. Get index page to extract sitekey
    index_url = f"{BASE_URL}/index.php"
    resp = session.get(index_url)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")
    script_tag = soup.find("script", string=re.compile(r"turnstile\.render"))
    if not script_tag:
        raise RuntimeError("Could not find turnstile.render script")
    match = re.search(r'sitekey:\s*"([^"]+)"', script_tag.string)
    if not match:
        raise RuntimeError("Could not extract sitekey")
    sitekey = match.group(1)
    print(f"Extracted sitekey: {sitekey}")

    # 2. Solve Turnstile challenge
    token = solve_turnstile(sitekey, index_url)
    print(f"Received Turnstile token: {token[:20]}...")

    # 3. Submit the form with the token (do not auto-follow redirects)
    data = {"cf-turnstile-response": token}
    post_resp = session.post(index_url, data=data, allow_redirects=False)
    print(f"POST response status: {post_resp.status_code}")

    # 4. Manually follow redirects
    final_resp = follow_redirects(session, post_resp)
    print(f"Final URL: {final_resp.url}")
    print(f"Final status: {final_resp.status_code}")

    # 5. Check if we got the credentials page
    if "IPTV account information" not in final_resp.text:
        # Dump a snippet for debugging
        snippet = final_resp.text[:500]
        print("Response snippet:", snippet)
        raise RuntimeError("Failed to reach credentials page")

    soup = BeautifulSoup(final_resp.text, "html.parser")
    user_input = soup.find("input", {"id": "accUser"})
    pass_input = soup.find("input", {"id": "accPass"})
    if not user_input or not pass_input:
        raise RuntimeError("Credentials fields not found on page")

    username = user_input.get("value", "").strip()
    password = pass_input.get("value", "").strip()
    if not username or not password:
        raise RuntimeError("Username or password is empty")

    print(f"New credentials: username={username}, password={password}")
    return username, password


def update_m3u_file(file_path: str, new_user: str, new_pass: str) -> None:
    """Replace all occurrences of old IPTV credentials in lit.m3u with the new ones."""
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Find existing credentials from any URL pattern in the file
    pattern = r"http://freeiptv\.ottc\.xyz:80/live/(\d+)/(\d+)/"
    matches = re.findall(pattern, content)
    if not matches:
        raise RuntimeError("No existing credentials found in lit.m3u")

    old_user, old_pass = matches[0]
    print(f"Old credentials found: username={old_user}, password={old_pass}")

    # Replace all occurrences with the new ones
    new_content = re.sub(
        pattern,
        f"http://freeiptv.ottc.xyz:80/live/{new_user}/{new_pass}/",
        content,
    )
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(new_content)

    print("lit.m3u updated successfully")


def main():
    try:
        username, password = fetch_credentials()
        m3u_path = "languages/lit.m3u"
        if not os.path.isfile(m3u_path):
            raise FileNotFoundError(f"Could not find {m3u_path}")

        update_m3u_file(m3u_path, username, password)
    except Exception as e:
        print(f"Script failed: {e}")
        raise


if __name__ == "__main__":
    main()