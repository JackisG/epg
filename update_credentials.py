import os
import re
import sys
import time
import requests
from bs4 import BeautifulSoup
from urllib.parse import quote, unquote, urlsplit


def normalize_proxy_url(proxy_value):
    """Return a URL-encoded HTTP proxy URL from a Webshare endpoint."""
    proxy_value = proxy_value.strip()
    if not proxy_value:
        raise ValueError("WEBSHARE_PROXY_URL is empty.")

    if "://" not in proxy_value:
        # Also accept Webshare's Host:Port:Username:Password export format.
        parts = proxy_value.split(":", 3)
        if len(parts) == 4 and parts[1].isdigit():
            host, port, username, password = parts
            proxy_value = f"http://{username}:{password}@{host}:{port}"

    if "://" not in proxy_value:
        proxy_value = f"http://{proxy_value}"

    scheme, authority = proxy_value.split("://", 1)
    if scheme.lower() != "http" or "@" not in authority:
        raise ValueError(
            "Use http://USERNAME:PASSWORD@HOST:PORT (or HOST:PORT:USERNAME:PASSWORD)."
        )

    credentials, host_port = authority.rsplit("@", 1)
    username, separator, password = credentials.partition(":")
    if not separator or not username or not password:
        raise ValueError("The Webshare proxy URL must contain a username and password.")

    parsed = urlsplit(f"http://{host_port}")
    if not parsed.hostname or not parsed.port:
        raise ValueError("The Webshare proxy URL must contain a valid host and port.")

    host = parsed.hostname
    if ":" in host:
        host = f"[{host}]"
    encoded_username = quote(unquote(username), safe="")
    encoded_password = quote(unquote(password), safe="")
    return f"http://{encoded_username}:{encoded_password}@{host}:{parsed.port}"


def get_proxy_dict(proxy_url):
    """Return a requests-compatible proxy mapping."""
    return {
        "http": proxy_url,
        "https": proxy_url,
    }


def solve_turnstile_2captcha(sitekey, page_url, api_key, proxy_url=None):
    print("Submitting Turnstile challenge to 2captcha...")
    in_url = "https://2captcha.com/in.php"

    payload = {
        "key": api_key,
        "method": "turnstile",
        "sitekey": sitekey,
        "pageurl": page_url,
        "json": 1
    }

    # Pass proxy to 2captcha so the token is solved from the same residential IP
    if proxy_url:
        parsed = urlsplit(proxy_url)
        proxy_str = f"{parsed.hostname}:{parsed.port}"
        if parsed.username and parsed.password:
            proxy_str = f"{unquote(parsed.username)}:{unquote(parsed.password)}@{proxy_str}"
        payload["proxytype"] = "HTTP"
        payload["proxy"] = proxy_str
        print(f"2captcha will solve via proxy: {parsed.hostname}:{parsed.port}")

    r = requests.post(in_url, data=payload, timeout=30)
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
        }, timeout=10)
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

    proxy_url = os.environ.get("WEBSHARE_PROXY_URL")
    if not proxy_url:
        print("Error: WEBSHARE_PROXY_URL environment variable is missing.")
        sys.exit(1)

    try:
        proxy_url = normalize_proxy_url(proxy_url)
    except ValueError as error:
        print(f"Error: Invalid WEBSHARE_PROXY_URL: {error}")
        sys.exit(1)

    parsed = urlsplit(proxy_url)
    print(f"Using Webshare proxy: {parsed.hostname}:{parsed.port}")

    site_url = "https://freeiptv2023-d.ottc.xyz/index.php"
    sitekey = "0x4AAAAAAA_Qtby-wpbozX7J"
    proxies = get_proxy_dict(proxy_url)

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate",
        "Connection": "keep-alive",
    }

    session = requests.Session()
    session.headers.update(headers)
    session.proxies = proxies

    # Step 1: GET the page to obtain session cookie
    print(f"GET {site_url} via proxy...")
    r = session.get(site_url, timeout=30)
    print(f"GET status: {r.status_code} | Cookies: {dict(session.cookies)}")

    if "connected to a VPN" in r.text:
        print("Error: Proxy IP is still detected as VPN/proxy by the site.")
        sys.exit(1)

    # Step 2: Solve Turnstile via 2captcha using the same proxy IP
    token = solve_turnstile_2captcha(sitekey, site_url, api_key, proxy_url)

    # Step 3: POST form with solved Turnstile token through same proxy
    print("POSTing form with Turnstile token...")
    post_headers = {
        **headers,
        "Content-Type": "application/x-www-form-urlencoded",
        "Origin": "https://freeiptv2023-d.ottc.xyz",
        "Referer": site_url,
    }
    post_data = {"cf-turnstile-response": token}
    r = session.post(site_url, data=post_data, headers=post_headers, timeout=30, allow_redirects=True)
    print(f"POST status: {r.status_code} | Final URL: {r.url}")

    # Check for errors
    if "connected to a VPN" in r.text:
        print("Error: Site still blocking as VPN/proxy after POST.")
        with open("error_page.html", "w", encoding="utf-8") as f:
            f.write(r.text)
        sys.exit(1)

    if "Are you a robot" in r.text:
        print("Error: Turnstile token was rejected by the site (robot check failed).")
        with open("error_page.html", "w", encoding="utf-8") as f:
            f.write(r.text)
        sys.exit(1)

    # Step 4: Navigate to view page if needed
    if "accUser" not in r.text:
        print("Navigating to index.php?action=view...")
        r = session.get("https://freeiptv2023-d.ottc.xyz/index.php?action=view", timeout=30)
        print(f"View page status: {r.status_code} | URL: {r.url}")

    # Step 5: Parse credentials
    soup = BeautifulSoup(r.text, "html.parser")
    user_elem = soup.find("input", {"id": "accUser"})
    pass_elem = soup.find("input", {"id": "accPass"})

    if not user_elem or not pass_elem:
        print("Error: Could not find #accUser or #accPass in response page.")
        with open("error_page.html", "w", encoding="utf-8") as f:
            f.write(r.text)
        sys.exit(1)

    new_username = user_elem.get("value", "").strip()
    new_password = pass_elem.get("value", "").strip()
    print(f"Successfully retrieved IPTV credentials -> Username: {new_username}, Password: {new_password}")

    # Step 6: Update languages/lit.m3u
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
