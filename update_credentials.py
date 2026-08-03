import os
import sys
import time
import requests
import json
import re
from datetime import datetime
import pytz
from bs4 import BeautifulSoup
from twocaptcha import TwoCaptcha
from base64 import b64encode
from nacl.public import PublicKey, SealedBox

def check_time():
    # Bypass time check if FORCE_RUN is set to 'true' (via workflow_dispatch)
    if os.getenv('FORCE_RUN', 'false').lower() == 'true':
        print("✅ FORCE_RUN is enabled. Bypassing Vilnius time check.")
        return True
        
    vilnius_tz = pytz.timezone('Europe/Vilnius')
    now = datetime.now(vilnius_tz)
    current_hour = now.hour
    current_minute = now.minute
    
    # Only run between 5 AM and 6 AM Vilnius time
    if current_hour < 5:
        print(f"⏳ Current time in Vilnius is {current_hour}:{current_minute}. Skipping execution until 5 AM.")
        return False
    return True

def solve_turnstile(api_key, site_key, url):
    solver = TwoCaptcha(api_key)
    try:
        print("🧩 Sending Turnstile challenge to 2Captcha...")
        result = solver.turnstile(sitekey=site_key, url=url)
        print("✅ Turnstile solved successfully.")
        return result['code']
    except Exception as e:
        print(f"❌ Error solving Turnstile: {e}")
        sys.exit(1)

def get_credentials(token):
    url = "https://freeiptv2023-d.ottc.xyz/index.php"
    payload = {
        "cf-turnstile-response": token
    }
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36",
        "Content-Type": "application/x-www-form-urlencoded",
        "Origin": "https://freeiptv2023-d.ottc.xyz",
        "Referer": "https://freeiptv2023-d.ottc.xyz/index.php"
    }
    
    session = requests.Session()
    session.get(url, headers=headers)
    response = session.post(url, data=payload, headers=headers)
    
    if "IPTV account information" not in response.text:
        print("❌ Failed to retrieve credentials. Captcha might be invalid or page structure changed.")
        sys.exit(1)
        
    soup = BeautifulSoup(response.text, 'html.parser')
    text = soup.get_text()
    
    # Extracting credentials using Regex based on the site's text layout
    server_url = re.search(r'IPTV Server URL\s*([a-zA-Z0-9\-\.\/:_]+)', text)
    username = re.search(r'IPTV Username\s*([a-zA-Z0-9]+)', text)
    password = re.search(r'IPTV Password\s*([a-zA-Z0-9]+)', text)
    m3u_link = re.search(r'M3U Download Link\s*(http[s]?://[^\s]+)', text)
    
    if not all([server_url, username, password, m3u_link]):
        print("❌ Could not parse all credentials from the page.")
        print("Page text snippet:", text[:500])
        sys.exit(1)
        
    creds = {
        "IPTV_SERVER_URL": server_url.group(1).strip(),
        "IPTV_USERNAME": username.group(1).strip(),
        "IPTV_PASSWORD": password.group(1).strip(),
        "IPTV_M3U_LINK": m3u_link.group(1).strip()
    }
    
    print("✅ Credentials extracted successfully.")
    return creds

def encrypt_secret(public_key: str, secret_value: str) -> str:
    pk = PublicKey(public_key.encode("utf-8"))
    sealed_box = SealedBox(pk)
    encrypted = sealed_box.encrypt(secret_value.encode("utf-8"))
    return b64encode(encrypted).decode("utf-8")

def update_github_secrets(creds):
    token = os.getenv('GITHUB_TOKEN')
    repo = os.getenv('GITHUB_REPOSITORY')
    
    if not token or not repo:
        print("❌ Missing GITHUB_TOKEN or GITHUB_REPOSITORY environment variables.")
        return

    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json"
    }
    
    pub_key_url = f"https://api.github.com/repos/{repo}/actions/secrets/public-key"
    res = requests.get(pub_key_url, headers=headers).json()
    
    if 'key' not in res:
        print("❌ Failed to fetch repository public key. Ensure your PAT_TOKEN has 'repo' scope.")
        print(res)
        sys.exit(1)
        
    for secret_name, secret_value in creds.items():
        encrypted_value = encrypt_secret(res['key'], secret_value)
        secret_url = f"https://api.github.com/repos/{repo}/actions/secrets/{secret_name}"
        payload = {
            "encrypted_value": encrypted_value,
            "key_id": res['key_id']
        }
        r = requests.put(secret_url, headers=headers, json=payload)
        if r.status_code in [201, 204]:
            print(f"✅ Successfully updated secret: {secret_name}")
        else:
            print(f"❌ Failed to update {secret_name}: {r.text}")

if __name__ == "__main__":
    if not check_time():
        sys.exit(0)
        
    api_key = os.getenv('TWOCAPTCHA_API_KEY')
    site_key = "0x4AAAAAAA_Qtby-wpbozX7J" # Extracted from freeiptv2023-d.ottc.xyz
    url = "https://freeiptv2023-d.ottc.xyz/index.php"
    
    token = solve_turnstile(api_key, site_key, url)
    creds = get_credentials(token)
    update_github_secrets(creds)
    print("🎉 Workflow completed successfully.")