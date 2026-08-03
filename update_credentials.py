import os
import re
import time
import json
import requests
from bs4 import BeautifulSoup
from twocaptcha import TwoCaptcha

# --- Configuration ---
SITE_URL = "https://freeiptv2023-d.ottc.xyz/index.php"
SITE_KEY = "0x4AAAAAAA_Qtby-wpbozX7J"  # Extracted from the site's Turnstile config
API_KEY = os.environ.get("TWOCAPTCHA_API_KEY")

solver = TwoCaptcha(API_KEY)

def get_turnstile_token():
    print("🧩 Sending Turnstile challenge to 2Captcha...")
    try:
        result = solver.turnstile(
            sitekey=SITE_KEY,
            url=SITE_URL
        )
        print("✅ Turnstile solved successfully.")
        return result['code']
    except Exception as e:
        print(f"❌ 2Captcha error: {e}")
        return None

def extract_credentials(html_content):
    """
    Robust parser that handles tightly packed DOM text where labels 
    and values might be concatenated without spaces.
    """
    soup = BeautifulSoup(html_content, 'html.parser')
    creds = {}
    
    mapping = {
        "IPTV Server URL": "server",
        "IPTV Username": "username",
        "IPTV Password": "password",
        "M3U Download Link": "m3u",
        "Activation Time": "activation",
        "Expiration Time": "expiration"
    }
    
    # Strategy 1: Standard DOM Traversal
    for label, key in mapping.items():
        label_el = soup.find(string=re.compile(re.escape(label)))
        if label_el:
            parent = label_el.find_parent(['tr', 'div', 'li', 'p', 'table'])
            if parent:
                next_cell = parent.find_next(['td', 'div', 'span', 'a', 'input', 'strong'])
                if next_cell:
                    if next_cell.name == 'input':
                        creds[key] = next_cell.get('value', '').strip()
                    elif next_cell.name == 'a':
                        creds[key] = next_cell.get('href', next_cell.get_text()).strip()
                    else:
                        creds[key] = next_cell.get_text(strip=True)
        
        # Strategy 2: Regex Fallback for concatenated text (e.g. "IPTV Usernamejohndoe")
        if not creds.get(key):
            text = soup.get_text()
            next_labels = [re.escape(l) for l in mapping.keys() if l != label]
            # Capture everything between the current label and the next known label
            pattern = rf"{re.escape(label)}(.*?)(?:{'|'.join(next_labels)}|$)"
            match = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
            if match:
                val = match.group(1).strip()
                val = re.sub(r'\s+', ' ', val).strip() # Clean up whitespace
                if val:
                    creds[key] = val

    return creds

def main():
    token = get_turnstile_token()
    if not token:
        print("❌ Failed to get Turnstile token.")
        exit(1)

    session = requests.Session()
    # Use a realistic User-Agent to prevent Cloudflare from dropping the POST request
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36",
        "Referer": SITE_URL,
        "Origin": "https://freeiptv2023-d.ottc.xyz"
    })

    # 1. Establish Session (Crucial for Cloudflare & PHP Session Cookies)
    print("🌐 Initializing session and fetching cookies...")
    session.get(SITE_URL)
    time.sleep(2) # Mimic human delay to avoid rate limits

    # 2. Submit the POST request with the exact Turnstile parameter name
    print("📤 Submitting credentials request...")
    payload = {
        "cf-turnstile-response": token  # MUST be this exact key
    }
    
    response = session.post(SITE_URL, data=payload, allow_redirects=True)
    
    # 3. Verify and Parse
    if "IPTV account information" in response.text or "IPTV Server URL" in response.text:
        print("✅ Successfully reached the credentials page!")
        creds = extract_credentials(response.text)
        
        if creds.get("username") and creds.get("password"):
            print(f"🎯 Extracted Credentials: {json.dumps(creds, indent=2)}")
            
            # --- INSERT YOUR LOGIC TO UPDATE REPO / SAVE FILE HERE ---
            # Example: Save to a JSON file for the next workflow steps
            with open('credentials.json', 'w') as f:
                json.dump(creds, f)
            
        else:
            print("❌ Reached the page, but failed to parse credentials. DOM structure likely changed.")
            print("Debug HTML Snippet:", response.text[:1000])
            exit(1)
    else:
        print("❌ Failed to retrieve credentials. Captcha rejected or page structure changed.")
        print("Response Status:", response.status_code)
        print("Response Snippet:", response.text[:500])
        exit(1)

if __name__ == "__main__":
    main()