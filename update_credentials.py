import os
import re
import sys
import time
import requests
from bs4 import BeautifulSoup

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

def solve_turnstile(sitekey, page_url, api_key):
    print("Submitting Turnstile challenge to 2captcha with User-Agent...")
    in_url = "https://2captcha.com/in.php"
    payload = {
        "key": api_key,
        "method": "turnstile",
        "sitekey": sitekey,
        "pageurl": page_url,
        "useragent": USER_AGENT,
        "json": 1
    }
    r = requests.post(in_url, data=payload)
    res = r.json()
    if res.get("status") != 1:
        raise Exception(f"Failed to submit to 2captcha: {res}")
    
    captcha_id = res["request"]
    print(f"Captcha task submitted ID: {captcha_id}. Waiting for solution...")
    
    res_url = "https://2captcha.com/res.php"
    for _ in range(36): # Wait up to 3 minutes
        time.sleep(5)
        r = requests.get(res_url, params={
            "key": api_key,
            "action": "get",
            "id": captcha_id,
            "json": 1
        })
        res = r.json()
        if res.get("status") == 1:
            print("Captcha solved successfully!")
            return res["request"]
        elif res.get("request") != "CAPCHA_NOT_READY":
            raise Exception(f"2captcha error: {res}")
    
    raise Exception("2captcha timeout waiting for token.")

def main():
    api_key = os.environ.get("TWOCAPTCHA_API_KEY")
    if not api_key:
        print("Error: TWOCAPTCHA_API_KEY environment variable is missing.")
        sys.exit(1)
        
    site_url = "https://freeiptv2023-d.ottc.xyz/index.php"
    sitekey = "0x4AAAAAAA_Qtby-wpbozX7J"
    
    session = requests.Session()
    session.headers.update({
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Origin": "https://freeiptv2023-d.ottc.xyz",
        "Referer": "https://freeiptv2023-d.ottc.xyz/index.php",
    })
    
    # 1. Initial GET to establish session cookies
    print("Fetching initial page...")
    init_res = session.get(site_url)
    print(f"Initial GET Status: {init_res.status_code}, Cookies: {session.cookies.get_dict()}")
    
    # 2. Solve Cloudflare Turnstile CAPTCHA via 2captcha
    token = solve_turnstile(sitekey, site_url, api_key)
    
    # 3. Post form payload
    print("Submitting CAPTCHA response token...")
    post_data = {
        "cf-turnstile-response": token
    }
    
    # Handle redirects manually or allow automatic redirect
    response = session.post(site_url, data=post_data, allow_redirects=True)
    print(f"POST Response URL: {response.url}, Status: {response.status_code}")
    for h in response.history:
        print(f" Redirect: {h.status_code} -> {h.headers.get('Location')}")
    
    # Check if we landed on view page or need explicit GET
    if "action=view" not in response.url:
        print("Explicitly requesting action=view page...")
        response = session.get("https://freeiptv2023-d.ottc.xyz/index.php?action=view")
        
    soup = BeautifulSoup(response.text, "html.parser")
    user_elem = soup.find("input", {"id": "accUser"})
    pass_elem = soup.find("input", {"id": "accPass"})
    
    if not user_elem or not pass_elem:
        print("Failed to locate username or password on the response page.")
        print("Page title:", soup.title.string if soup.title else "No title")
        print("Page snippet:", response.text[:1000])
        sys.exit(1)
        
    new_username = user_elem.get("value", "").strip()
    new_password = pass_elem.get("value", "").strip()
    
    print(f"Obtained IPTV Credentials - Username: {new_username}, Password: {new_password}")
    
    # Update lit.m3u file
    m3u_path = os.path.join("languages", "lit.m3u")
    if not os.path.exists(m3u_path):
        if os.path.exists("lit.m3u"):
            m3u_path = "lit.m3u"
        else:
            print(f"Error: {m3u_path} not found.")
            sys.exit(1)
            
    with open(m3u_path, "r", encoding="utf-8") as f:
        content = f.read()
        
    pattern = r"(http://freeiptv\.ottc\.xyz:\d+/live/)[^/]+/[^/]+/"
    replacement = rf"\g<1>{new_username}/{new_password}/"
    
    updated_content = re.sub(pattern, replacement, content)
    
    param_pattern = r"(freeiptv\.ottc\.xyz:\d+/get\.php\?username=)[^&]+(&password=)[^&]+"
    updated_content = re.sub(param_pattern, rf"\g<1>{new_username}\g<2>{new_password}", updated_content)
    
    with open(m3u_path, "w", encoding="utf-8") as f:
        f.write(updated_content)
        
    print(f"Successfully updated credentials in {m3u_path}")

if __name__ == "__main__":
    main()
