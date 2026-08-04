import os
import re
import sys
import time
import requests
from playwright.sync_api import sync_playwright

def solve_turnstile_2captcha(sitekey, page_url, user_agent, api_key):
    print("Submitting Turnstile challenge to 2captcha...")
    in_url = "https://2captcha.com/in.php"
    payload = {
        "key": api_key,
        "method": "turnstile",
        "sitekey": sitekey,
        "pageurl": page_url,
        "useragent": user_agent,
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
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-accelerated-2d-canvas",
                "--no-first-run",
                "--no-zygote",
                "--disable-gpu"
            ]
        )
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 720},
            device_scale_factor=1,
        )
        page = context.new_page()
        page.set_default_timeout(60000)
        
        # Mask navigator.webdriver
        page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            window.navigator.chrome = { runtime: {} };
        """)
        
        print(f"Navigating to {site_url}...")
        page.goto(site_url, wait_until="domcontentloaded", timeout=60000)
        user_agent = page.evaluate("navigator.userAgent")
        
        time.sleep(3)
        
        # Attempt to click Turnstile iframe directly
        print("Attempting to interact with Turnstile iframe...")
        try:
            for frame in page.frames:
                if "challenges.cloudflare.com" in frame.url:
                    print("Found Turnstile iframe, clicking body/checkbox...")
                    frame.click("body", timeout=5000)
                    break
        except Exception as e:
            print(f"Turnstile iframe click note: {e}")
            
        # Check if button becomes enabled
        solved_natively = False
        try:
            page.wait_for_selector("#create-btn:not([disabled])", timeout=12000)
            print("Turnstile verified natively in browser!")
            solved_natively = True
        except Exception:
            print("Turnstile not solved natively within timeout. Using 2captcha...")

        if not solved_natively:
            if not api_key:
                print("Error: TWOCAPTCHA_API_KEY environment variable missing.")
                sys.exit(1)
                
            token = solve_turnstile_2captcha(sitekey, site_url, user_agent, api_key)
            
            # Inject token into hidden input and enable button
            page.evaluate("""(token) => {
                let input = document.querySelector('input[name="cf-turnstile-response"]');
                if (!input) {
                    input = document.createElement('input');
                    input.type = 'hidden';
                    input.name = 'cf-turnstile-response';
                    document.querySelector('form').appendChild(input);
                }
                input.value = token;
                
                const btn = document.querySelector('#create-btn');
                if (btn) btn.removeAttribute('disabled');
            }""", token)

        print("Clicking submit button...")
        page.click("#create-btn")
        
        print("Waiting for credentials page...")
        time.sleep(5)
        
        if "action=view" not in page.url:
            print(f"URL is currently {page.url}, attempting navigation to index.php?action=view...")
            page.goto("https://freeiptv2023-d.ottc.xyz/index.php?action=view", wait_until="domcontentloaded")

        try:
            page.wait_for_selector("#accUser", timeout=20000)
            new_username = page.input_value("#accUser").strip()
            new_password = page.input_value("#accPass").strip()
            print(f"Successfully retrieved IPTV credentials -> Username: {new_username}, Password: {new_password}")
        except Exception:
            print(f"Error: Failed to find #accUser element. Current URL: {page.url}")
            print("Page title:", page.title())
            print("Page Content Snippet:\n", page.content()[:1500])
            browser.close()
            sys.exit(1)
            
        browser.close()

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