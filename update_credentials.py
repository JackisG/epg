"""
update_credentials.py

Uses Oxylabs BrowserAgent (oxylabs-ai-studio) to open the site, click
'Create free IPTV account', wait for turnstile and redirect, extract
accUser and accPass, and update languages/lit.m3u.

This version robustly handles different return types from the agent (DataModel, dict,
string, bytes), converts them to HTML strings, saves debug_output.html, and parses
the HTML for credentials.
"""

import os
import re
import sys
import json
import time
import logging
from typing import Tuple, Optional, Any
from bs4 import BeautifulSoup

# Try to import BrowserAgent; handle missing package gracefully
try:
    from oxylabs_ai_studio.apps.browser_agent import BrowserAgent
except Exception:
    BrowserAgent = None

TARGET_URL = "https://freeiptv2023-d.ottc.xyz"
FILE_PATH = "languages/lit.m3u"
DEBUG_HTML = "debug_output.html"

# Logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("update_credentials")

OXYLABS_API_KEY = os.environ.get("OXYLABS_API_KEY")


def stringify_agent_output(obj: Any) -> str:
    """
    Convert various possible agent output types to a plain HTML string.
    - If obj has attribute 'content' (DataModel), use it.
    - If obj has attribute 'data', take data and unwrap it.
    - If obj is dict, try to find 'content' or 'data' keys; else json.dumps.
    - If obj is bytes, decode.
    - Otherwise use str(obj).
    """
    try:
        # Unwrap wrapper that may hold `.data`
        if hasattr(obj, "data"):
            obj = getattr(obj, "data")

        # DataModel-like with .content
        if hasattr(obj, "content"):
            candidate = getattr(obj, "content")
            if isinstance(candidate, bytes):
                return candidate.decode("utf-8", errors="replace")
            return str(candidate)

        # If it's already a string
        if isinstance(obj, str):
            return obj

        # If bytes
        if isinstance(obj, (bytes, bytearray)):
            return obj.decode("utf-8", errors="replace")

        # If dict-like
        if isinstance(obj, dict):
            for key in ("content", "html", "data", "body", "text"):
                if key in obj and isinstance(obj[key], (str, bytes)):
                    val = obj[key]
                    if isinstance(val, (bytes, bytearray)):
                        return val.decode("utf-8", errors="replace")
                    return str(val)
            # as a last resort, JSON-serialize
            return json.dumps(obj, ensure_ascii=False, indent=2)

        # If it's an object with .text()
        if hasattr(obj, "text"):
            try:
                t = obj.text()
                if isinstance(t, (str, bytes)):
                    return t.decode("utf-8", errors="replace") if isinstance(t, (bytes, bytearray)) else t
            except TypeError:
                # maybe .text is property
                t = getattr(obj, "text")
                if isinstance(t, (str, bytes)):
                    return t.decode("utf-8", errors="replace") if isinstance(t, (bytes, bytearray)) else t

        # Fallback to str()
        return str(obj)
    except Exception:
        log.exception("Error while stringifying agent output; returning repr(obj)")
        try:
            return repr(obj)
        except Exception:
            return ""


def save_debug_html(content: Any, note: str = None) -> None:
    """
    Save diagnostic HTML or string-like content to DEBUG_HTML. Accepts DataModel or other objects
    returned by the Oxylabs agent and stringifies them safely.
    """
    try:
        html = stringify_agent_output(content)
        with open(DEBUG_HTML, "w", encoding="utf-8") as fh:
            if note:
                fh.write("<!-- NOTE: " + str(note).replace("--", "") + " -->\n")
            fh.write(html)
        log.info("Saved debug HTML to %s (len=%d)", DEBUG_HTML, len(html))
    except Exception:
        log.exception("Failed to save debug HTML")


def looks_like_credentials(u: str, p: str) -> bool:
    """
    Heuristic: valid credentials are digit-only sequences (observed on site),
    with length >= 6.
    """
    if not u or not p:
        return False
    return bool(re.fullmatch(r"\d{6,}", u) and re.fullmatch(r"\d{6,}", p))


def extract_creds_from_html(html: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Extract accUser / accPass from HTML using several ordered strategies.
    Returns (user, pass) or (None, None).
    """
    if not html:
        return None, None

    soup = BeautifulSoup(html, "lxml")

    # 1) By id
    try:
        ue = soup.find(id="accUser")
        pe = soup.find(id="accPass")
        if ue and pe:
            u = (ue.get("value") or ue.get_text(strip=True) or "").strip()
            p = (pe.get("value") or pe.get_text(strip=True) or "").strip()
            log.debug("ID lookup found: %r / %r", u[:60], p[:60])
            if looks_like_credentials(u, p):
                log.info("Extracted numeric credentials from #accUser/#accPass")
                return u, p
            else:
                log.info("Found #accUser/#accPass but values do not match numeric pattern")
    except Exception:
        log.debug("ID extraction failed", exc_info=True)

    # 2) input[name=...] fallback
    try:
        ue = soup.find("input", attrs={"name": "accUser"}) or soup.find("input", attrs={"name": "user"})
        pe = soup.find("input", attrs={"name": "accPass"}) or soup.find("input", attrs={"name": "pass"})
        if ue and pe:
            u = (ue.get("value") or "").strip()
            p = (pe.get("value") or "").strip()
            log.debug("Named input lookup found: %r / %r", u[:60], p[:60])
            if looks_like_credentials(u, p):
                log.info("Extracted numeric credentials from input[name=...]")
                return u, p
    except Exception:
        log.debug("Named input extraction failed", exc_info=True)

    # 3) /live/<digits>/<digits> pattern anywhere
    m = re.search(r'/live/(\d{6,})/(\d{6,})', html)
    if m:
        u, p = m.group(1), m.group(2)
        log.info("Found /live/<digits>/<digits> in HTML: %s / %s", u, p)
        if looks_like_credentials(u, p):
            return u, p

    # 4) First two long digit sequences on page
    nums = re.findall(r'\d{6,}', html)
    if len(nums) >= 2:
        u, p = nums[0], nums[1]
        log.info("Found long digit sequences in HTML: %s / %s", u, p)
        if looks_like_credentials(u, p):
            return u, p

    # 5) Links with ottc.xyz/live
    try:
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if "ottc.xyz" in href and "/live/" in href:
                m = re.search(r'/live/(\d{6,})/(\d{6,})', href)
                if m:
                    u, p = m.group(1), m.group(2)
                    log.info("Found credentials in href: %s -> %s / %s", href[:120], u, p)
                    if looks_like_credentials(u, p):
                        return u, p
    except Exception:
        log.debug("Link scanning failed", exc_info=True)

    return None, None


def run_oxylabs_agent_retrieve(retries: int = 3, wait_between: int = 3) -> Tuple[Optional[str], Optional[str]]:
    """
    Use Oxylabs BrowserAgent to load the site and perform the click + extraction.
    Robustly handles returned object types and retries.
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
            "Include any relevant XHR/response bodies if available. Extract the values inside elements with id='accUser' and id='accPass' if present."
        ),
        "output_format": "html",
    }

    attempt = 0
    while attempt < retries:
        attempt += 1
        try:
            log.info("Oxylabs BrowserAgent run attempt %d/%d", attempt, retries)
            result = agent.run(**payload)

            # Convert whatever the agent returned into a string/html
            html = stringify_agent_output(result)
            if not html or not html.strip():
                log.warning("Oxylabs agent returned empty content on attempt %d", attempt)
                time.sleep(wait_between)
                continue

            # Save raw agent output for debugging
            save_debug_html(html, note=f"oxylabs-agent-attempt-{attempt}")

            # Try extracting credentials
            u, p = extract_creds_from_html(html)
            if u and p:
                log.info("Credentials successfully extracted from Oxylabs output")
                return u, p

            log.info("Oxylabs returned HTML but no credentials extracted (attempt %d).", attempt)
            time.sleep(wait_between)

        except Exception:
            log.exception("Oxylabs agent run failed on attempt %d", attempt)
            time.sleep(wait_between)

    return None, None


def update_m3u_file(new_user: str, new_pass: str) -> bool:
    """
    Replace credentials inside languages/lit.m3u for ottc.xyz/live URLs.
    Returns True if file updated.
    """
    log.info("Updating %s with new credentials", FILE_PATH)
    try:
        with open(FILE_PATH, "r", encoding="utf-8") as fh:
            txt = fh.read()
    except FileNotFoundError:
        log.error("File not found: %s", FILE_PATH)
        return False

    # Strict pattern requiring ottc.xyz to avoid affecting CDN/bootstrap links
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
        log.warning("No matching ottc.xyz/live links found to update.")
        return False

    with open(FILE_PATH, "w", encoding="utf-8") as fh:
        fh.write(new_txt)
    log.info("Updated %d links in %s", n, FILE_PATH)
    return True


def main():
    try:
        user, pwd = run_oxylabs_agent_retrieve(retries=3, wait_between=4)
        if not user or not pwd:
            log.error("Could not obtain credentials from Oxylabs BrowserAgent. Check debug_output.html artifact.")
            sys.exit(1)

        log.info("Retrieved credentials (masked): user=%s..., pass=%s...", user[:6], pwd[:6])

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