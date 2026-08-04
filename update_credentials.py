import os
import re
import sys
import time
import requests
from playwright.sync_api import sync_playwright

def solve_turnstile_2captcha(sitekey, page_url, api_key):
    print("Submitting Turnstile challenge to 2captcha...")
    in_url = "https://2captcha.com/in.php"
    payload = {
        "key": api_key,
        "method": "turnstile",
        "sitekey": sitekey,
        "pageurl": page_url,
        "json": 1
    }
    r = requests.post(in_url, data=payload)
    res = r.json()
    if res.get("status") != 1:
        raise Exception(f"Failed to submit to 2captcha: {res}")
    
    captcha_id = res["request"]
    print(f"Captcha task submitted ID: {captcha_id}. Waiting for solution...")
    
    res_url = "https://2captcha.com/res.php"
    for _ in range(36):
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
    site_url = "https://freeiptv2023-d.ottc.xyz/index.php"
    sitekey = "0x4AAAAAAA_Qtby-wpbozX7J"
    
    with sync_playwright() as p:
        print("Launching Chromium browser...")
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = context.new_page()
        page.set_default_timeout(60000)
        
        print(f"Navigating to {site_url}...")
        # Use domcontentloaded to prevent networkidle timeouts from persistent background requests
        page.goto(site_url, wait_until="domcontentloaded", timeout=60000)
        
        # Wait up to 10 seconds to check if Turnstile auto-verifies
        auto_solved = False
        try:
            page.wait_for_selector("#create-btn:not([disabled])", timeout=10000)
            print("Turnstile auto-verified by browser!")
            auto_solved = True
        except Exception:
            print("Turnstile did not auto-solve within 10s. Solved via 2captcha...")

        if not auto_solved:
            if not api_key:
                print("Error: TWOCAPTCHA_API_KEY environment variable missing.")
                sys.exit(1)
                
            token = solve_turnstile_2captcha(sitekey, site_url, api_key)
            
            # Inject token into DOM and enable submit button
            page.evaluate("""(token) => {
                let input = document.querySelector('input[name="cf-turnstile-response"]');
                if (!input) {
                    input = document.createElement('input');
                    input.type = 'hidden';
                    input.name = 'cf-turnstile-response';
                    document.querySelector('form').appendChild(input);
                }
                input.value = token;
                document.querySelector('#create-btn').removeAttribute('disabled');
            }""", token)
        
        print("Clicking submit button...")
        page.click("#create-btn")
        
        print("Waiting for credentials page to load...")
        page.wait_for_selector("#accUser", timeout=30000)
        
        new_username = page.input_value("#accUser").strip()
        new_password = page.input_value("#accPass").strip()
        
        print(f"Successfully retrieved IPTV credentials -> Username: {new_username}, Password: {new_password}")
        
        browser.close()

    # Update playlist file
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