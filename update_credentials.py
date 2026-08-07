"""
Robust updater for freeiptv credentials.

- Uses Playwright to render the page and pass Cloudflare turnstile (by waiting for the challenge to complete).
- Clicks the 'Create free IPTV account' control.
- Waits for elements with id="accUser" and id="accPass" (and fallbacks) to appear and contain values.
- Saves debug_output.html always (for diagnostics).
- Replaces credentials in languages/lit.m3u using robust regex with fallbacks.
"""

import os
import re
import sys
import time
import logging
from bs4 import BeautifulSoup

TARGET_URL = "https://freeiptv2023-d.ottc.xyz"
FILE_PATH = "languages/lit.m3u"
DEBUG_HTML = "debug_output.html"

# Set up logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("update_credentials")

OXYLABS_USERNAME = os.environ.get("OXYLABS_USERNAME")
OXYLABS_PASSWORD = os.environ.get("OXYLABS_PASSWORD")


def save_debug_html(content, note=None):
    try:
        with open(DEBUG_HTML, "w", encoding="utf-8") as fh:
            if note:
                fh.write("<!-- NOTE: " + note.replace("--", "") + " -->\n")
            fh.write(content)
        log.info("Saved debug HTML to %s", DEBUG_HTML)
    except Exception:
        log.exception("Failed to save debug HTML")


def extract_from_html_fallback(html):
    """
    Multiple fallback extraction attempts on the rendered HTML.
    Returns (username, password) or (None, None).
    """
    soup = BeautifulSoup(html, "lxml")

    # 1) Direct ID lookup (inputs)
    try:
        user_el = soup.find(id="accUser")
        pass_el = soup.find(id="accPass")
        if user_el:
            u = user_el.get("value") or user_el.get_text(strip=True)
        else:
            u = None
        if pass_el:
            p = pass_el.get("value") or pass_el.get_text(strip=True)
        else:
            p = None
        if u and p:
            log.info("Found credentials via #accUser/#accPass elements.")
            return u.strip(), p.strip()
    except Exception:
        log.debug("ID lookup failed", exc_info=True)

    # 2) Look for input elements with name attributes
    try:
        user_el = soup.find("input", attrs={"name": "accUser"}) or soup.find("input", attrs={"name": "user"})
        pass_el = soup.find("input", attrs={"name": "accPass"}) or soup.find("input", attrs={"name": "pass"})
        if user_el and pass_el:
            u = user_el.get("value") or ""
            p = pass_el.get("value") or ""
            if u and p:
                log.info("Found credentials via input[name=...] elements.")
                return u.strip(), p.strip()
    except Exception:
        log.debug("Named input lookup failed", exc_info=True)

    # 3) Regex-based search for typical inline patterns (/live/<user>/<pass>/ and others)
    patterns = [
        r'id=["\']?accUser["\']?[^>]*value=["\']?([^"\'>\s]+)',
        r'id=["\']?accPass["\']?[^>]*value=["\']?([^"\'>\s]+)',
        r'value=["\']?([^"\'>\s]+)[^>]*id=["\']?accUser["\']?',
        r'value=["\']?([^"\'>\s]+)[^>]*id=["\']?accPass["\']?',
        r'//[^/]+/live/([^/]+)/([^/]+)',  # /live/<user>/<pass> style
        r'([A-Za-z0-9._%+-]+)[:\s]+([A-Za-z0-9._%+-]{6,})'  # generic user:pass-ish
    ]
    for p in patterns:
        m = re.search(p, html, re.IGNORECASE | re.DOTALL)
        if m:
            if m.lastindex and m.lastindex >= 2:
                u = m.group(1)
                v = m.group(2)
                log.info("Found credentials via regex pattern: %s", p)
                return u.strip(), v.strip()
            else:
                u = m.group(1).strip()
                rest = html[m.end():m.end() + 500]
                m2 = re.search(r'(["\']|:|\s)([A-Za-z0-9._%+-]{6,})', rest)
                if m2:
                    p = m2.group(2)
                    return u, p
    return None, None


def update_m3u_file(new_username, new_password):
    log.info("Updating file: %s", FILE_PATH)
    try:
        with open(FILE_PATH, "r", encoding="utf-8") as fh:
            content = fh.read()
    except FileNotFoundError:
        log.error("File not found: %s", FILE_PATH)
        return False

    # Match host variants and /live/<user>/<pass>/... pattern
    pattern = re.compile(
        r'(https?://(?:www\.)?freeiptv(?:\d*-d)?\.ottc\.xyz(?::\d+)?/live/)([^/]+)/([^/]+)(/[^ \n"\']*)',
        flags=re.IGNORECASE,
    )
    replacement = r'\1' + re.escape(new_username) + '/' + re.escape(new_password) + r'\4'

    new_content, count = pattern.subn(replacement, content)
    if count == 0:
        log.warning("No links matched the expected freeiptv pattern. Trying a permissive replacement...")

        # permissive: replace first path segment after /live/ with new creds
        permissive = re.compile(r'(https?://[^/]*freeiptv[^/]*?/live/)([^/]+)(/[^ \n"\']*)', flags=re.IGNORECASE)
        new_content, count2 = permissive.subn(lambda m: f"{m.group(1)}{new_username}/{new_password}{m.group(3) or ''}", content)
        if count2 == 0:
            log.warning("Permissive replacement also found nothing. No edits made.")
            return False
        else:
            log.info("Permissive replacement updated %d links.", count2)
    else:
        log.info("Updated %d links.", count)

    with open(FILE_PATH, "w", encoding="utf-8") as fh:
        fh.write(new_content)
    log.info("File saved: %s", FILE_PATH)
    return True


def fetch_credentials_with_playwright(url, max_wait_seconds=180):
    """
    Uses Playwright to render the page, click the 'Create free IPTV account' control,
    and wait for accUser & accPass to appear and contain values.
    Returns (username, password) on success, or (None, None).
    """
    try:
        from playwright.sync_api import sync_playwright, TimeoutError as PWTimeoutError
    except Exception:
        log.exception("Playwright not installed or available.")
        return None, None

    log.info("Launching Playwright browser to visit %s", url)
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
            page = context.new_page()

            target = url.rstrip("/") + "/index.php"
            log.info("Going to %s", target)
            try:
                # increase timeout to 120s for slow Cloudflare / site responses
                page.goto(target, wait_until="networkidle", timeout=120000)
            except PWTimeoutError:
                log.warning("Page.goto timed out after 120s — saving partial content and continuing.")
                try:
                    html_partial = page.content()
                    save_debug_html(html_partial, note="Partial content after goto timeout")
                except Exception:
                    log.debug("Could not read page content after timeout.", exc_info=True)
                # continue — page may continue loading

            # attempt to find and click the create button using multiple selectors
            create_selectors = [
                "text=Create free IPTV account",
                "text=Create Free IPTV Account",
                "text=Create free iptv account",
                "#create-btn",
                "button:has-text(\"Create free IPTV account\")",
                "a:has-text(\"Create free IPTV account\")",
            ]

            clicked = False
            for sel in create_selectors:
                try:
                    locator = page.locator(sel)
                    if locator.count() > 0:
                        log.info("Found create control using selector: %s", sel)
                        try:
                            locator.first.scroll_into_view_if_needed(timeout=5000)
                        except Exception:
                            pass
                        try:
                            locator.first.click(timeout=8000)
                            clicked = True
                            log.info("Clicked create control (%s).", sel)
                            break
                        except Exception as e:
                            log.debug("Click attempt failed for %s: %s", sel, e)
                except Exception:
                    continue

            if not clicked:
                # Use a single-line JS string (no triple-quoted Python string) to avoid parsing issues
                try:
                    js = "const btn = Array.from(document.querySelectorAll('button,a')).find(el => /create\\s+free\\s*iptv/i.test(el.textContent)); if (btn) { btn.scrollIntoView(); btn.click(); return true; } return false;"
                    js_clicked = page.evaluate(js)
                    log.info("Attempted JS-click for create control (result=%s).", js_clicked)
                except Exception:
                    log.debug("JS-click attempt failed.", exc_info=True)

            # wait loop for accUser / accPass or fallback extraction
            deadline = time.time() + max_wait_seconds
            while time.time() < deadline:
                try:
                    user_present = page.locator("#accUser").count() > 0
                    pass_present = page.locator("#accPass").count() > 0

                    u_val = None
                    p_val = None
                    if user_present:
                        try:
                            u_el = page.locator("#accUser").first
                            u_val = u_el.get_attribute("value") or (u_el.input_value() if hasattr(u_el, "input_value") else None) or u_el.inner_text() or None
                        except Exception:
                            try:
                                u_val = page.eval_on_selector("#accUser", "el => el.value || el.innerText || ''")
                            except Exception:
                                u_val = None
                    if pass_present:
                        try:
                            p_el = page.locator("#accPass").first
                            p_val = p_el.get_attribute("value") or (p_el.input_value() if hasattr(p_el, "input_value") else None) or p_el.inner_text() or None
                        except Exception:
                            try:
                                p_val = page.eval_on_selector("#accPass", "el => el.value || el.innerText || ''")
                            except Exception:
                                p_val = None

                    if u_val and p_val:
                        u_val = u_val.strip()
                        p_val = p_val.strip()
                        log.info("Credentials found via DOM: %s / %s", u_val[:6] + "...", p_val[:6] + "...")
                        html = page.content()
                        save_debug_html(html, note="Success: accUser/accPass found in DOM via Playwright")
                        return u_val, p_val

                    # fallback: inspect full rendered HTML for /live/<user>/<pass>/ or other patterns
                    html = page.content()
                    u2, p2 = extract_from_html_fallback(html)
                    if u2 and p2:
                        log.info("Credentials found via fallback regex on rendered HTML.")
                        save_debug_html(html, note="Success: found via regex fallback on rendered HTML")
                        return u2, p2

                except Exception as e:
                    log.debug("Loop exception while waiting for credentials: %s", e, exc_info=True)

                time.sleep(2)

            # timed out waiting for credentials
            html = page.content()
            save_debug_html(html, note="Timeout: credentials not found within wait period")
            log.error("Timed out waiting for credentials (max %s seconds).", max_wait_seconds)
            return None, None

    except Exception:
        log.exception("Playwright flow failed.")
        return None, None


def get_credentials():
    # Try Playwright first (handles JS and Cloudflare turnstile rendering better)
    u, p = fetch_credentials_with_playwright(TARGET_URL, max_wait_seconds=180)
    if u and p:
        return u, p

    # Oxylabs fallback if credentials are available
    if OXYLABS_USERNAME and OXYLABS_PASSWORD:
        log.info("Attempting Oxylabs realtime API fallback.")
        try:
            import requests

            payload = {
                "source": "universal",
                "url": TARGET_URL,
                "render": "html",
                "stealth": True,
                "wait": 15000,
            }
            resp = requests.post("https://realtime.oxylabs.io/v1/queries", auth=(OXYLABS_USERNAME, OXYLABS_PASSWORD), json=payload, timeout=120)
            resp.raise_for_status()
            data = resp.json()
            content = None
            try:
                content = data["results"][0]["content"]
            except Exception:
                content = None
            if content:
                save_debug_html(content, note="Oxylabs fallback raw content")
                u2, p2 = extract_from_html_fallback(content)
                if u2 and p2:
                    return u2, p2
                else:
                    log.error("Oxylabs content parsed but credentials not found.")
            else:
                log.error("Oxylabs returned unexpected structure: %s", data)
        except Exception:
            log.exception("Oxylabs fallback failed.")

    # Final direct GET fallback
    try:
        import requests

        log.info("Final fallback: direct requests.get to target (no rendering).")
        r = requests.get(TARGET_URL, timeout=30, headers={"User-Agent": "Mozilla/5.0"})
        if r.status_code == 200 and r.text:
            save_debug_html(r.text, note="Final fallback: direct requests.get response")
            u3, p3 = extract_from_html_fallback(r.text)
            if u3 and p3:
                return u3, p3
    except Exception:
        log.debug("Direct GET fallback failed.", exc_info=True)

    log.error("All attempts failed to extract credentials.")
    return None, None


def main():
    try:
        user, pwd = get_credentials()
        if not user or not pwd:
            log.error("Failed to obtain credentials. See debug_output.html artifact for details.")
            sys.exit(1)

        log.info("Updating m3u file with obtained credentials.")
        ok = update_m3u_file(user, pwd)
        if not ok:
            log.error("Failed to update m3u file with new credentials.")
            sys.exit(1)

        log.info("Successfully updated file. User: %s (masked), Pass: %s (masked)", user[:4] + "...", pwd[:4] + "...")
        sys.exit(0)

    except Exception:
        log.exception("Unhandled error in main.")
        sys.exit(1)


if __name__ == "__main__":
    main()