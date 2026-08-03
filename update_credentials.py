import os
import re
import time
import random
import string
import requests
from bs4 import BeautifulSoup
from twocaptcha import TwoCaptcha

BASE_URL = "https://freeiptv2023-d.ottc.xyz"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
TWO_CAPTCHA_API_KEY = os.environ.get("TWO_CAPTCHA_API_KEY")

if not TWO_CAPTCHA_API_KEY:
    raise RuntimeError("TWO_CAPTCHA_API_KEY environment variable not set")

SITEKEY = "0x4AAAAAAA_Qtby-wpbozX7J"


def solve_turnstile(sitekey: str, page_url: str) -> str:
    """Solve Cloudflare Turnstile using 2Captcha and return the token."""
    solver = TwoCaptcha(TWO_CAPTCHA_API_KEY)
    # Generate a random cData (some sites require it)
    cdata = ''.join(random.choices(string.ascii_letters + string.digits, k=12))
    try:
        result = solver.turnstile(
            sitekey=sitekey,
            url=page_url,
            action="submit",
            cdata=cdata,
            timeout=120
        )
        return result["code"]
    except Exception as e:
        print(f"2Captcha error: {e}")
        raise


def fetch_credentials(max_attempts=3) -> tuple[str, str]:
    """Attempt to fetch credentials with retries if token is rejected."""
    for attempt in range(max_attempts):
        print(f"\nAttempt {attempt+1}/{max_attempts}")
        session = requests.Session()
        session.headers.update({
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate",
            "DNT": "1",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "Cache-Control": "max-age=0",
        })

        # 1. Get index page to establish session
        index_url = f"{BASE_URL}/index.php"
        resp = session.get(index_url)
        resp.raise_for_status()
        print("Initial GET status:", resp.status_code)

        # 2. Solve Turnstile
        print(f"Using sitekey: {SITEKEY}")
        token = solve_turnstile(SITEKEY, index_url)
        print(f"Received token: {token[:30]}...")

        # 3. Wait a few seconds to let the token become active
        time.sleep(3)

        # 4. Submit the token
        data = {"cf-turnstile-response": token}
        post_headers = {
            "Origin": BASE_URL,
            "Referer": index_url,
            "Content-Type": "application/x-www-form-urlencoded",
        }
        post_resp = session.post(index_url, data=data, headers=post_headers, timeout=30)
        print(f"POST final URL: {post_resp.url}")
        print(f"POST final status: {post_resp.status_code}")

        # 5. Check if we reached the credentials page
        if "IPTV account information" in post_resp.text:
            break
        else:
            print("Token rejected, retrying...")
            # Print a small snippet for debugging
            snippet = post_resp.text[:500]
            print("Snippet:", snippet)
            # If it's the last attempt, raise an error
            if attempt == max_attempts - 1:
                raise RuntimeError("Failed to reach credentials page after multiple attempts")
            # Otherwise, wait and continue loop
            time.sleep(5)
            continue

    # 6. Extract credentials
    soup = BeautifulSoup(post_resp.text, "html.parser")
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

    pattern = r"http://freeiptv\.ottc\.xyz:80/live/(\d+)/(\d+)/"
    matches = re.findall(pattern, content)
    if not matches:
        raise RuntimeError("No existing credentials found in lit.m3u")

    old_user, old_pass = matches[0]
    print(f"Old credentials found: username={old_user}, password={old_pass}")

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