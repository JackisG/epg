import os
import re
import sys
import time
import requests
from bs4 import BeautifulSoup


def get_proxy_from_env():
    """Return a tuple (proxy_for_2captcha, requests_proxies_dict) or None if no proxy configured.
    proxy_for_2captcha should be in the form expected by 2captcha (login:pass@host:port or host:port)
    requests_proxies_dict is a dict suitable for requests.Session.proxies (with scheme).
    """
    proxy = os.environ.get("WEBSHARE_PROXY_URL") or os.environ.get("HTTPS_PROXY") or os.environ.get("HTTP_PROXY")
    if not proxy:
        return None

    # Strip any scheme for the 2captcha payload
    stripped = proxy
    if stripped.startswith("http://"):
        stripped = stripped[len("http://"):]
    elif stripped.startswith("https://"):
        stripped = stripped[len("https://"):]

    # Build requests proxies dict (use http scheme)
    requests_proxy = {"http": f"http://{stripped}", "https": f"http://{stripped}"}
    return stripped, requests_proxy

def solve_turnstile(sitekey, page_url, api_key, proxy=None):
    print(f"Submitting Turnstile challenge to 2captcha...")
    in_url = "https://2captcha.com/in.php"
    payload = {
        "key": api_key,
        "method": "turnstile",
        "sitekey": sitekey,
        "pageurl": page_url,
        "json": 1
    }

    # If a proxy is provided, instruct 2captcha to use that proxy for the worker that visits the target site.
    # 2captcha expects proxy in the form login:password@host:port or host:port and proxytype (HTTP/HTTPS).
    if proxy:
        print(f"2captcha will solve via proxy: {proxy}")
        payload["proxy"] = proxy
        payload["proxytype"] = "HTTP"

    r = requests.post(in_url, data=payload)
    res = r.json()
    if res.get("status") != 1:
        raise Exception(f"Failed to submit to 2captcha: {res}")
    
    captcha_id = res["request"]
    print(f"Captcha task submitted ID: {captcha_id}. Waiting for solution...")
    
    res_url = "https://2captcha.com/res.php"
    for _ in range(30):
        time.sleep(5)
        r = requests.get(res_url, params={
            "key": api_key,
            "action": "get",
            "id": captcha_id,
            "json": 1
        })
        res = r.json()
        if res.get("status") == 1:
            print("2captcha solved token successfully!")
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
    # Disable using environment proxies and control proxies explicitly
    session.trust_env = False

    proxy_info = get_proxy_from_env()
    proxy_str = None
    if proxy_info:
        proxy_str, proxy_dict = proxy_info
        print(f"Using Webshare proxy: {proxy_str}")
        session.proxies.update(proxy_dict)

    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": site_url,
    })
    
    # Initial GET to establish session cookies
    print("Fetching initial page...")
    resp = session.get(site_url)
    print(f"GET status: {resp.status_code} | Cookies: {session.cookies.get_dict()}")
    
    # Solve Cloudflare Turnstile CAPTCHA
    token = solve_turnstile(sitekey, site_url, api_key, proxy_str)
    
    # Post form payload
    print("Submitting CAPTCHA response token...")
    post_data = {
        "cf-turnstile-response": token
    }
    
    response = session.post(site_url, data=post_data)
    
    # Fetch view page if redirect not automatically followed to view
    if "action=view" not in response.url:
        response = session.get("https://freeiptv2023-d.ottc.xyz/index.php?action=view")
        
    soup = BeautifulSoup(response.text, "html.parser")
    user_elem = soup.find("input", {"id": "accUser"})
    pass_elem = soup.find("input", {"id": "accPass"})
    
    if not user_elem or not pass_elem:
        print("Failed to locate username or password on the response page.")
        print("Page snippet:", response.text[:1000])
        sys.exit(1)
        
    new_username = user_elem.get("value", "").strip()
    new_password = pass_elem.get("value", "").strip()
    
    print(f"Obtained IPTV Credentials - Username: {new_username}, Password: {new_password}")
    
    # Update lit.m3u file
    m3u_path = os.path.join("languages", "lit.m3u")
    if not os.path.exists(m3u_path):
        # Fallback to local path if directly in working dir
        if os.path.exists("lit.m3u"):
            m3u_path = "lit.m3u"
        else:
            print(f"Error: {m3u_path} not found.")
            sys.exit(1)
            
    with open(m3u_path, "r", encoding="utf-8") as f:
        content = f.read()
        
    # Regex to replace username and password in freeiptv links
    # Target structure: http://freeiptv.ottc.xyz:80/live/<USERNAME>/<PASSWORD>/<STREAM_ID>.ts
    pattern = r"(http://freeiptv\.ottc\.xyz:\d+/live/)[^/]+/[^/]+/"
    replacement = rf"\g<1>{new_username}/{new_password}/"
    
    updated_content = re.sub(pattern, replacement, content)
    
    # Also update any m3u query param URLs if present (e.g. get.php?username=...&password=...)
    param_pattern = r"(freeiptv\.ottc\.xyz:\d+/get\.php\?username=)[^&]+(&password=)[^&]+"
    updated_content = re.sub(param_pattern, rf"\g<1>{new_username}\g<2>{new_password}", updated_content)
    
    with open(m3u_path, "w", encoding="utf-8") as f:
        f.write(updated_content)
        
    print(f"Successfully updated credentials in {m3u_path}")

if __name__ == "__main__":
    main()
