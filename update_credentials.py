"""
update_credentials.py

Uses Oxylabs BrowserAgent (oxylabs-ai-studio) to open the site, click
'Create free IPTV Account', wait for turnstile and redirect, extract
accUser and accPass, and update languages/lit.m3u.

Saves debug_output.html and update_credentials.log for diagnostics.
"""

import os
import re
import sys
import time
import logging
from typing import Tuple, Optional
from bs4 import BeautifulSoup

# Oxylabs BrowserAgent import (from oxylabs-ai-studio)
try:
    from oxylabs_ai_studio.apps.browser_agent import BrowserAgent
except Exception:
    BrowserAgent = None  # handled at runtime

TARGET_URL = "https://freeiptv2023-d.ottc.xyz"
FILE_PATH = "languages/lit.m3u"
DEBUG_HTML = "debug_output.html"

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("update_credentials")

OXYLABS_API_KEY = os.environ.get("OXYLABS_API_KEY")


def save_debug_html(content: str, note: str = None) -> None:
    try:
        with open(DEBUG_HTML, "w", encoding="utf-8") as fh:
            if note:
                fh.write("<!-- NOTE: " + note.replace("--", "") + " -->\n")
            fh.write(content)
        log.info("Saved debug HTML to %s", DEBUG_HTML)
    except Exception:
        log.exception("Failed to save debug HTML")


def looks_like_credentials(u: str, p: str) -> bool:
    """
    Heuristic: valid credentials on this site are digit-only sequences with length >= 6.
    """
    if not u or not p:
        return False
    return bool(re.fullmatch(r"\d{6,}", u) and re.fullmatch(r"\d{6,}", p))


def extract_creds_from_html(html: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Extract accUser / accPass from HTML using several deterministic strategies.
    Returns (user, pass) or (None, None).
    """
    soup = BeautifulSoup(html, "lxml")

    # 1) Direct by id
    try:
        ue = soup.find(id="accUser")
        pe = soup.find(id="accPass")
        if ue and pe:
            u = (ue.get("value") or ue.get_text(strip=True) or "").strip()
            p = (pe.get("value") or pe.get_text(strip=True) or "").strip()
            log.debug("ID lookup produced: %r / %r", u[:50], p[:50])
            if looks_like_credentials(u, p):
                log.info("Extracted numeric credentials from #accUser/#accPass")
                return u, p
            else:
                log.info("Found #accUser/#accPass but values don't match expected numeric pattern.")
    except Exception:
        log.debug("ID lookup failed", exc_info=True)

    # 2) input[name=...] variants
    try:
        ue = soup.find("input", attrs={"name": "accUser"}) or soup.find("input", attrs={"name": "user"})
        pe = soup.find("input", attrs={"name": "accPass"}) or soup.find("input", attrs={"name": "pass"})
        if ue and pe:
            u = (ue.get("value") or "").strip()
            p = (pe.get("value") or "").strip()
            log.debug("Named input lookup produced: %r / %r", u[:50], p[:50])
            if looks_like_credentials(u, p):
                log.info("Extracted numeric credentials from input[name=...]")
                return u, p
    except Exception:
        log.debug("Named input lookup failed", exc_info=True)

    # 3) Search for /live/<digits>/<digits> pattern in HTML
    m = re.search(r'/live/(\d{6,})/(\d{6,})', html)
    if m:
        u, p = m.group(1), m.group(2)
        log.info("Found /live/<digits>/<digits> pattern in HTML: %s / %s", u, p)
        if looks_like_credentials(u, p):
            return u, p

    # 4) Find long digit sequences anywhere, pick first two (fallback)
    nums = re.findall(r'\d{6,}', html)
    if len(nums) >= 2:
        u, p = nums[0], nums[1]
        log.info("Found long digit sequences in HTML, picking first two: %s / %s", u, p)
        if looks_like_credentials(u, p):
            return u, p

    # 5) Scan links for ottc.xyz/live/<digits>/<digits>
    try:
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if "ottc.xyz" in href and "/live/" in href:
                m = re.search(r'/live/(\d{6,})/(\d{6,})', href)
                if m:
                    u, p = m.group(1), m.group(2)
                    log.info("Found credentials in href %s -> %s / %s", href[:150], u, p)
                    if looks_like_credentials(u, p):
                        return u, p
    except Exception:
        log.debug("Link scanning failed", exc_info=True)

    return None, None


def run_oxylabs_agent_retrieve(retries: int = 2, wait_between: int = 3) -> Tuple[Optional[str], Optional[str]]:
    """
    Use Oxylabs BrowserAgent to load the site and perform the click + extraction.
    Returns (user, pass) or (None, None).
    """
    if BrowserAgent is None:
        log.error("oxylabs-ai-studio BrowserAgent not installed or import failed.")
        return None, None
    if not OXYLABS_API_KEY:
        log.error("OXYLABS_API_KEY environment variable not set.")
        return None, None

    agent = BrowserAgent(api_key=OXYLABS_API_KEY)

    payload = {
        "url": TARGET_URL,
        "user_prompt": (
            "Click the button labeled 'Create free IPTV account', solve any Cloudflare turnstile challenge, "
            "wait for the redirect or account info to appear, and return the resulting page HTML. "
            "Also include any XHR or response bodies you saw. "
            "Extract the values inside elements with id='accUser' and id='accPass' if present."
        ),
        "output_format": "html"
    }

    attempt = 0
    while attempt < retries:
        attempt += 1
        try:
            log.info("Oxylabs BrowserAgent run attempt %d/%d", attempt, retries)
            result = agent.run(**payload)
            # result.data is typically the agent output (HTML)
            html = ""
            try:
                html = result.data if hasattr(result, "data") else str(result)
            except Exception:
                html = str(result)
            if not html:
                log.warning("Oxylabs agent returned empty result on attempt %d", attempt)
                time.sleep(wait_between)
                continue

            save_debug_html(html, note=f"oxylabs-agent-attempt-{attempt}")
            u, p = extract_creds_from_html(html)
            if u and p:
                return u, p

            # no creds found; wait and retry
            log.info("Oxylabs returned HTML but no credentials extracted (attempt %d).", attempt)
            time.sleep(wait_between)

        except Exception:
            log.exception("Oxylabs agent run failed on attempt %d", attempt)
            time.sleep(wait_between)

    return None, None


def update_m3u_file(new_user: str, new_pass: str) -> bool:
    """
    Replace credentials inside languages/lit.m3u for ottc.xyz/freeiptv-style URLs.
    Returns True if file updated; False otherwise.
    """
    log.info("Updating %s with new credentials", FILE_PATH)
    try:
        with open(FILE_PATH, "r", encoding="utf-8") as fh:
            txt = fh.read()
    except FileNotFoundError:
        log.error("File not found: %s", FILE_PATH)
        return False

    # Strict pattern: require 'ottc.xyz' in host so unrelated CDN links are not matched
    pattern = re.compile(
        r'(https?://[^/\s]*ottc\.xyz(?::\d+)?/live/)([^/]+)/([^/\s]+)(/[^ \n"\']*)?',
        flags=re.IGNORECASE,
    )

    def repl(m):
        prefix = m.group(1)
        suffix = m.group(4) or ""
        return f"{prefix}{new_user}/{new_pass}{suffix}"

    new_txt, n = pattern.subn(repl, txt)

    if n == 0:
        log.warning("No ottc.xyz/live links found to update.")
        return False

    with open(FILE_PATH, "w", encoding="utf-8") as fh:
        fh.write(new_txt)
    log.info("Updated %d links in %s", n, FILE_PATH)
    return True


def main():
    try:
        # Retrieve credentials via Oxylabs BrowserAgent
        user, pwd = run_oxylabs_agent_retrieve(retries=3, wait_between=4)
        if not user or not pwd:
            log.error("Could not obtain credentials from Oxylabs BrowserAgent. Check debug_output.html artifact.")
            sys.exit(1)

        log.info("Retrieved credentials (masked): user=%s..., pass=%s...", user[:6], pwd[:6])

        # Validate before updating
        if not looks_like_credentials(user, pwd):
            log.error("Extracted credentials do not match expected numeric format: %r / %r", user, pwd)
            sys.exit(1)

        if not update_m3u_file(user, pwd):
            log.error("Failed to update m3u file.")
            sys.exit(1)

        log.info("Successfully updated %s", FILE_PATH)
        sys.exit(0)

    except Exception:
        log.exception("Unhandled error")
        sys.exit(1)


if __name__ == "__main__":
    main()