import os
import re
import sys
import time
import requests
from bs4 import BeautifulSoup
from twocaptcha import TwoCaptcha

API_KEY = os.getenv('TWOCAPTCHA_API_KEY')
BASE_URL = "https://freeiptv2023-d.ottc.xyz"
INDEX_URL = f"{BASE_URL}/index.php"
VIEW_URL = f"{BASE_URL}/index.php?action=view"

def main():
    # 1. Initialize Session FIRST to persist cookies and TLS fingerprint
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": BASE_URL,
        "Origin": BASE_URL
    })

    # 2. Fetch initial page and cookies BEFORE solving captcha
    print("🌐 Initializing session and fetching cookies...")
    resp = session.get(INDEX_URL)
    if resp.status_code != 200:
        print(f"❌ Failed to load main page: {resp.status_code}")
        sys.exit(1)
        
    # 3. Extract Sitekey dynamically (fallback to known sitekey from HAR)
    match = re.search(r'sitekey:\s*["\']([0-9A-Za-z_-]+)["\']', resp.text)
    sitekey = match.group(1) if match else "0x4AAAAAAA_Qtby-wpbozX7J"
    print(f"🔑 Using Sitekey: {sitekey}")

    # 4. Solve Captcha
    print("🧩 Sending Turnstile challenge to 2Captcha...")
    try:
        solver = TwoCaptcha(API_KEY)
        result = solver.turnstile(
            sitekey=sitekey,
            url=INDEX_URL,
            invisible=1,
            action="",
            cData=""
        )
        token = result['code']
        print("✅ Turnstile solved successfully.")
    except Exception as e:
        print(f"❌ Failed to solve Turnstile: {e}")
        sys.exit(1)

    # 5. Submit POST request IMMEDIATELY using the SAME session
    print("📤 Submitting credentials request...")
    post_data = {
        "cf-turnstile-response": token  # Crucial: This is the exact field name Turnstile expects
    }
    
    # Post to the same URL (form action is empty)
    resp = session.post(INDEX_URL, data=post_data, allow_redirects=True)
    
    # The site might redirect to ?action=view or require a manual GET using the established session
    if "?action=view" not in resp.url and "IPTV account information" not in resp.text:
        print("🔄 Following redirect to credentials view...")
        resp = session.get(VIEW_URL)

    # 6. Parse Credentials
    if "IPTV account information" in resp.text or "IPTV Server URL" in resp.text:
        print("✅ Credentials retrieved successfully!")
        soup = BeautifulSoup(resp.text, 'html.parser')
        
        # Extract credentials (Adjust selectors if the site structure changes)
        text = soup.get_text(separator='\n', strip=True)
        print("📜 Raw Credentials Text Snippet:")
        print(text[:500])
        
        # TODO: Add your logic here to parse Server URL, Username, Password, M3U Link
        # and update your repository files/commit via GITHUB_TOKEN.
        
    else:
        print("❌ Failed to retrieve credentials. Captcha rejected or page structure changed.")
        print("Response Status:", resp.status_code)
        print("Response Snippet:", resp.text[:500])
        sys.exit(1)

if __name__ == "__main__":
    main()