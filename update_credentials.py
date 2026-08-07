"""
credentials.py

Playwright-based scraper to obtain free IPTV account credentials from:
  https://freeiptv2023-d.ottc.xyz/index.php

Behavior:
- Opens the page with Playwright (headless), navigates to /index.php.
- Attempts to click the "Create free IPTV account" control (many selector fallbacks).
- Waits for elements with id="accUser" and id="accPass" to be present and populated.
- Saves debug_output.html for diagnostics in all code paths where HTML is available.
- Replaces credentials in languages/lit.m3u for matching freeiptv URLs.
- Contains fallbacks: regex extraction from rendered HTML and optional Oxylabs API fallback
  (if OXYLABS_USERNAME and OXYLABS_PASSWORD are supplied in env).
"""

import os
import re
import sys
import time
import logging
from typing import Tuple, Optional

from bs4 import BeautifulSoup

TARGET_URL = "https://freeiptv2023-d.ottc.xyz"
FILE_PATH = "languages/lit.m3u"
DEBUG_HTML = "debug_output.html"

# Logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("credentials")

OXYLABS_USERNAME = os.environ.get("OXYLABS_USERNAME")
OXYLABS_PASSWORD = os.environ.get("OXYLABS_PASSWORD")


def save_debug_html(html: str, note: Optional[str] = None) -> None:
    try:
        with open(DEBUG_HTML, "w", encoding="utf-8") as fh:
            if note:
                fh.write("<!-- NOTE: " + note.replace("--", "") + " -->\n")
            fh.write(html)
        log.info("Saved debug HTML to %s", DEBUG_HTML)
    except Exception:
        log.exception("Failed saving debug HTML")


def extract_credentials_from_html(html: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Attempt multiple extraction strategies from HTML:
    1) Direct id lookup (#accUser / #accPass)
    2) Input[name=...] lookup
    3) Regex patterns (inline /live/<user>/<pass>/, user:pass, id/value attributes)
    """
    try:
        soup = BeautifulSoup(html, "lxml")
    except Exception:
        soup = BeautifulSoup(html, "html.parser")

    # 1) Direct id lookup
    try:
        user_el = soup.find(id="accUser")
        pass_el = soup.find(id="accPass")
        if user_el and pass_el:
            u = user_el.get("value") or user_el.get_text(strip=True)
            p = pass_el.get("value") or pass_el.get_text(strip=True)
            if u and p:
                return u.strip(), p.strip()
    except Exception:
        log.debug("Direct id lookup failed", exc_info=True)

    # 2) input[name=...] fallback
    try:
        user_el = soup.find("input", attrs={"name": "accUser"}) or soup.find("input", attrs={"name": "user"})
        pass_el = soup.find("input", attrs={"name": "accPass"}) or soup.find("input", attrs={"name": "pass"})
        if user_el and pass_el:
            u = user_el.get("value") or ""
            p = pass_el.get("value") or ""
            if u and p:
                return u.strip(), p.strip()
    except Exception:
        log.debug("Named input lookup failed", exc_info=True)

    # 3) Regex-based searches
    patterns = [
        # /live/<user>/<pass>
        r'//[^/]+/live/([^/]+)/([^/]+)',
        # id="accUser" value="..."
        r'id=["\']?accUser["\']?[^>]*value=["\']?([^"\'>\s]+)',
        r'id=["\']?accPass["\']?[^>]*value=["\']?([^"\'>\s]+)',
        # generic user:pass or user | pass labels
        r'([A-Za-z0-9._%+-]{4,})[:\s]+([A-Za-z0-9._%+-]{4,})'
    ]
    for pat in patterns:
        m = re.search(pat, html, re.IGNORECASE | re.DOTALL)
        if m:
            if m.lastindex and m.lastindex >= 2:
                u = m.group(1).strip()
                p = m.group(2).strip()
                # discard obviously wrong captures
                if len(u) >= 3 and len(p) >= 3:
                    return u, p

    return None, None


def update_m3u_file(new_user: str, new_pass: str) -> bool:
    """
    Replace credentials in languages/lit.m3u for freeiptv links.
    Replaces the two path segments immediately after /live/ with new_user/new_pass when possible.
    """
    log.info("Updating file %s", FILE_PATH)
    try:
        with open(FILE_PATH, "r", encoding="utf-8") as fh:
            content = fh.read()
    except FileNotFoundError:
        log.error("M3U file not found: %s", FILE_PATH)
        return False

    # Strict pattern: host variants + /live/<user>/<pass> + optional suffix
    strict = re.compile(
        r'(https?://(?:www\.)?freeiptv(?:\d*-d)?\.ottc\.xyz(?::\d+)?/live/)([^/]+)/([^/]+)(?=/|[\s"\']|$)',
        flags=re.IGNORECASE,
    )

    def repl_strict(m):
        prefix = m.group(1)
        suffix = ""
        return f"{prefix}{new_user}/{new_pass}{suffix}"

    new_content, count = strict.subn(repl_strict, content)
    if count == 0:
        # Permissive replacement: replace the first two path segments after /live/ if present
        permissive = re.compile(r'(https?://[^/]*freeiptv[^/]*/live/)([^/\s"\']+)(/[^ \n"\']*)?', flags=re.IGNORECASE)

        def repl_perm(m):
            prefix = m.group(1)
            tail = m.group(3) or ""
            return f"{prefix}{new_user}/{new_pass}{tail}"

        new_content, count = permissive.subn(repl_perm, content)

    if count == 0:
        log.warning("No links updated (no matching freeiptv links found).")
        return False

    with open(FILE_PATH, "w", encoding="utf-8") as fh:
        fh.write(new_content)
    log.info("Updated %d link(s) in %s", count, FILE_PATH)
    return True


def fetch_with_playwright(url: str, max_wait_seconds: int = 180) -> Tuple[Optional[str], Optional[str]]:
    """
    Use Playwright to open the page, click Create button and wait for accUser/accPass to populate.
    Returns (user, pass) or (None, None).
    """
    try:
        from playwright.sync_api import sync_playwright, TimeoutError as PWTimeoutError
    except Exception:
        log.exception("Playwright import failed")
        return None, None

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
            page = context.new_page()

            target = url.rstrip("/") + "/index.php"
            log.info("Navigating to %s", target)
            try:
                page.goto(target, wait_until="networkidle", timeout=120000)
            except PWTimeoutError:
                log.warning("page.goto timed out after 120s, capturing partial content and continuing.")
                try:
                    save_debug_html(page.content(), note="partial after goto timeout")
                except Exception:
                    log.debug("Could not capture partial page content", exc_info=True)

            # Try multiple selectors to find the create control
            create_selectors = [
                "text=Create free IPTV account",
                "text=Create Free IPTV Account",
                "text=Create free iptv account",
                "#create-btn",
                "button:has-text(\"Create free IPTV account\")",
                "a:has-text(\"Create free IPTV account\")",
                "button:has-text(\"Create Free IPTV Account\")",
            ]
            clicked = False
            for sel in create_selectors:
                try:
                    locator = page.locator(sel)
                    if locator.count() > 0:
                        log.info("Clicking create control using selector: %s", sel)
                        try:
                            locator.first.scroll_into_view_if_needed(timeout=3000)
                        except Exception:
                            pass
                        try:
                            locator.first.click(timeout=8000)
                            clicked = True
                            break
                        except Exception:
                            log.debug("Click failed for %s", sel, exc_info=True)
                except Exception:
                    continue

            if not clicked:
                # JS fallback: single-line string
                try:
                    js = "const btn = Array.from(document.querySelectorAll('button,a')).find(el => /create\\s+free\\s*iptv/i.test(el.textContent)); if (btn) { btn.scrollIntoView(); btn.click(); return true; } return false;"
                    res = page.evaluate(js)
                    log.info("JS click attempted, result=%s", res)
                except Exception:
                    log.debug("JS click attempt failed", exc_info=True)

            # Poll for accUser / accPass or fallback extraction
            deadline = time.time() + max_wait_seconds
            while time.time() < deadline:
                try:
                    # Check DOM inputs
                    try:
                        user_present = page.locator("#accUser").count() > 0
                        pass_present = page.locator("#accPass").count() > 0
                    except Exception:
                        user_present = False
                        pass_present = False

                    u_val = None
                    p_val = None
                    if user_present:
                        try:
                            u_el = page.locator("#accUser").first
                            u_val = u_el.get_attribute("value") or (u_el.input_value() if hasattr(u_el, "input_value") else None) or u_el.inner_text()
                        except Exception:
                            try:
                                u_val = page.eval_on_selector("#accUser", "el => el.value || el.innerText || ''")
                            except Exception:
                                u_val = None
                    if pass_present:
                        try:
                            p_el = page.locator("#accPass").first
                            p_val = p_el.get_attribute("value") or (p_el.input_value() if hasattr(p_el, "input_value") else None) or p_el.inner_text()
                        except Exception:
                            try:
                                p_val = page.eval_on_selector("#accPass", "el => el.value || el.innerText || ''")
                            except Exception:
                                p_val = None

                    if u_val and p_val:
                        u_val = u_val.strip()
                        p_val = p_val.strip()
                        html = page.content()
                        save_debug_html(html, note="success: accUser/accPass found in DOM")
                        return u_val, p_val

                    # Fallback: inspect rendered html
                    html = page.content()
                    u2, p2 = extract_credentials_from_html(html)
                    if u2 and p2:
                        save_debug_html(html, note="found via regex on rendered HTML")
                        return u2, p2

                except Exception:
                    log.debug("Polling loop exception", exc_info=True)

                time.sleep(2)

            # timeout
            try:
                html = page.content()
                save_debug_html(html, note="timeout waiting for credentials")
            except Exception:
                log.debug("Could not capture page content on timeout", exc_info=True)
            log.error("Timed out waiting for credentials")
            return None, None

    except Exception:
        log.exception("Playwright flow failed")
        return None, None


def fetch_with_oxylabs(url: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Optional Oxylabs realtime API fallback (requires OXYLABS_USERNAME & OXYLABS_PASSWORD).
    Will render HTML server-side and return results for parsing.
    """
    if not OXYLABS_USERNAME or not OXYLABS_PASSWORD:
        log.info("Oxylabs credentials not present; skipping Oxylabs fallback.")
        return None, None

    import requests

    payload = {
        "source": "universal",
        "url": url,
        "render": "html",
        "stealth": True,
        "wait": 15000,
    }
    try:
        resp = requests.post("https://realtime.oxylabs.io/v1/queries", auth=(OXYLABS_USERNAME, OXYLABS_PASSWORD), json=payload, timeout=120)
        resp.raise_for_status()
        data = resp.json()
        content = None
        try:
            content = data["results"][0]["content"]
        except Exception:
            content = None
        if content:
            save_debug_html(content, note="oxylabs_fallback_content")
            u, p = extract_credentials_from_html(content)
            if u and p:
                return u, p
    except Exception:
        log.exception("Oxylabs request failed")
    return None, None


def get_credentials() -> Tuple[Optional[str], Optional[str]]:
    # Primary: Playwright render
    u, p = fetch_with_playwright(TARGET_URL, max_wait_seconds=180)
    if u and p:
        return u, p

    # Fallback 1: Oxylabs
    u, p = fetch_with_oxylabs(TARGET_URL)
    if u and p:
        return u, p

    # Fallback 2: direct requests.get (no JS)
    try:
        import requests

        log.info("Final direct GET fallback to %s", TARGET_URL)
        r = requests.get(TARGET_URL, timeout=30, headers={"User-Agent": "Mozilla/5.0"})
        if r.status_code == 200 and r.text:
            save_debug_html(r.text, note="direct_get_fallback")
            u, p = extract_credentials_from_html(r.text)
            if u and p:
                return u, p
    except Exception:
        log.debug("Direct GET fallback failed", exc_info=True)

    return None, None


def main():
    try:
        creds = get_credentials()
        if not creds or not creds[0] or not creds[1]:
            log.error("Failed to obtain credentials. See %s artifact for debug HTML.", DEBUG_HTML)
            sys.exit(1)

        user, pwd = creds
        log.info("Obtained credentials (masked): %s / %s", (user[:4] + "..."), (pwd[:4] + "..."))

        ok = update_m3u_file(user, pwd)
        if not ok:
            log.error("Failed to update m3u file with new credentials.")
            sys.exit(1)

        log.info("Successfully updated %s", FILE_PATH)
        sys.exit(0)

    except Exception:
        log.exception("Unhandled exception in main")
        sys.exit(1)


if __name__ == "__main__":
    main()