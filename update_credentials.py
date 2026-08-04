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

    headless_mode = os.environ.get("HEADLESS", "true").lower() == "true"

    # Webshare residential proxy URL from GitHub secret
    # Format: http://username:password@host:port
    proxy_url = os.environ.get("WEBSHARE_PROXY_URL")
    if not proxy_url:
        print("Error: WEBSHARE_PROXY_URL environment variable is missing.")
        sys.exit(1)

    print(f"Using Webshare proxy: {proxy_url.split('@')[-1]}")  # log only host:port, not credentials

    proxy_config = {"server": proxy_url}

    with sync_playwright() as p:
        print(f"Launching Chromium browser (headless={headless_mode})...")
        browser = p.chromium.launch(
            headless=headless_mode,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--window-size=1280,720",
            ]
        )

        context = browser.new_context(
            proxy=proxy_config,
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 720},
            locale="en-US",
            timezone_id="Europe/Vilnius"
        )
        page = context.new_page()
        page.set_default_timeout(60000)

        # Anti-detection stealth injections
        page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            window.chrome = { runtime: {} };
            Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']});
            Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
        """)

        print(f"Navigating to {site_url}...")
        page.goto(site_url, wait_until="domcontentloaded", timeout=60000)
        user_agent = page.evaluate("navigator.userAgent")

        print("Waiting for Cloudflare Turnstile widget to load...")
        solved_natively = False

        # Wait for Turnstile iframe and try native solve
        try:
            iframe_selector = "iframe[src*='challenges.cloudflare.com']"
            page.wait_for_selector(iframe_selector, timeout=25000)
            print("Turnstile iframe rendered! Clicking checkbox...")
            time.sleep(2)

            frame_locator = page.frame_locator(iframe_selector)
            try:
                frame_locator.locator("input[type='checkbox']").click(timeout=3000)
            except Exception:
                frame_locator.locator("body").click(timeout=3000)

            print("Clicked Turnstile checkbox. Waiting for verification...")
        except Exception as e:
            print(f"Turnstile iframe rendering note: {e}")

        # Poll for button unlock (native solve)
        for _ in range(15):
            btn = page.query_selector("#create-btn")
            if btn and not page.eval_on_selector("#create-btn", "el => el.disabled"):
                print("Turnstile verified natively!")
                solved_natively = True
                break
            time.sleep(1)

        # Fallback: 2captcha
        if not solved_natively:
            print("Turnstile not solved natively. Requesting token from 2captcha...")
            if not api_key:
                print("Error: TWOCAPTCHA_API_KEY environment variable missing.")
                sys.exit(1)

            token = solve_turnstile_2captcha(sitekey, site_url, user_agent, api_key)

            print("Injecting 2captcha token into form...")
            page.evaluate("""(token) => {
                const form = document.querySelector('form');
                let inputs = form.querySelectorAll('input[name="cf-turnstile-response"]');
                if (inputs.length === 0) {
                    let input = document.createElement('input');
                    input.type = 'hidden';
                    input.name = 'cf-turnstile-response';
                    input.value = token;
                    form.appendChild(input);
                } else {
                    inputs.forEach(i => i.value = token);
                }
                const btn = document.querySelector('#create-btn');
                if (btn) btn.removeAttribute('disabled');
                const waitMsg = document.querySelector('#please-wait');
                if (waitMsg) waitMsg.style.display = 'none';
            }""", token)

        print("Submitting form...")
        try:
            with page.expect_navigation(wait_until="domcontentloaded", timeout=30000):
                page.click("#create-btn")
        except Exception as e:
            print(f"Navigation note: {e}")

        print(f"URL after form submission: {page.url}")

        try:
            page.wait_for_selector("#accUser", timeout=20000)
            new_username = page.input_value("#accUser").strip()
            new_password = page.input_value("#accPass").strip()
            print(f"Successfully retrieved IPTV credentials -> Username: {new_username}, Password: {new_password}")
        except Exception:
            print("Saving error_page.png and error_page.html for debugging...")
            page.screenshot(path="error_page.png")
            with open("error_page.html", "w", encoding="utf-8") as f:
                f.write(page.content())
            print(f"Error: Failed to find #accUser element. Current URL: {page.url}")
            print("Page Title:", page.title())
            browser.close()
            sys.exit(1)

        browser.close()

    # Update languages/lit.m3u
    m3u_path = os.path.join("languages", "lit.m3u")
    if not os.path.exists(m3u_path):
        if os.path.exists("lit.m3u"):
            m3u_path = "lit.m3u"
        else:
            print(f"Error: {m3u_path} not found.")
            sys.exit(1)

    with open(m3u_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Replace username/password in stream URLs
    pattern = r"(http://freeiptv\.ottc\.xyz:\d+/live/)[^/]+/[^/]+/"
    replacement = rf"\g<1>{new_username}/{new_password}/"
    updated_content = re.sub(pattern, replacement, content)

    # Replace username/password in M3U playlist URLs
    param_pattern = r"(freeiptv\.ottc\.xyz:\d+/get\.php\?username=)[^&]+(&password=)[^&]+"
    updated_content = re.sub(param_pattern, rf"\g<1>{new_username}\g<2>{new_password}", updated_content)

    with open(m3u_path, "w", encoding="utf-8") as f:
        f.write(updated_content)

    print(f"Successfully updated credentials in {m3u_path}")


if __name__ == "__main__":
    main()
