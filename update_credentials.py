#!/usr/bin/env python3
"""
update_credentials.py (safer)

- Uses Oxylabs Realtime Web Scraper API to render the page and run a render_script that
  clicks the "Create free IPTV account" button and injects a machine-readable element.
- Extracts credentials only from safe sources (injected JSON, DOM IDs, or ottc.xyz/live/ pattern).
- Strict validation: both user and pass MUST be digit-only strings with length >= MIN_DIGITS.
- If safe credentials are not found, the script aborts WITHOUT modifying the M3U file.
- Saves debug_output.html for diagnostics and logs progress to stdout.
"""

import os
import re
import sys
import time
import json
import logging
from typing import Optional, Tuple, Any
import requests
from bs4 import BeautifulSoup

# Configuration
OXYLABS_USERNAME = os.environ.get("OXYLABS_USERNAME")
OXYLABS_PASSWORD = os.environ.get("OXYLABS_PASSWORD")
TARGET_URL = "https://freeiptv2023-d.ottc.xyz"
FILE_PATH = "languages/lit.m3u"
DEBUG_HTML = "debug_output.html"
OX_ENDPOINT = "https://realtime.oxylabs.io/v1/queries"

# Minimum digits required for username/password to be considered valid
MIN_DIGITS = 10

# Render script executed inside the remote browser by Oxylabs
RENDER_SCRIPT = r'''
(async function() {
  function wait(ms){return new Promise(r=>setTimeout(r,ms));}
  function textIncludesCreateIPTV(s){ s = (s||'').toLowerCase(); return s.includes('create') && s.includes('iptv'); }
  async function findButton(timeoutMs=30000){
    const start = Date.now();
    while (Date.now() - start < timeoutMs){
      const btn = Array.from(document.querySelectorAll('button,a')).find(el => textIncludesCreateIPTV(el.textContent));
      if (btn) return btn;
      await wait(500);
    }
    return null;
  }
  try{
    const btn = await findButton(30000);
    if (btn){
      // wait until enabled (max 20s)
      const startEnable = Date.now();
      while (Date.now() - startEnable < 20000){
        try { if (!btn.disabled && !btn.getAttribute('disabled')) break; } catch(e){}
        await wait(500);
      }
      try { btn.click(); } catch(e){
        try { btn.dispatchEvent(new MouseEvent('click', { bubbles: true })); } catch(e){}
      }
    }
    // Wait up to 60s for values to appear (longer to allow turnstile)
    let accUser=null, accPass=null;
    const startWait = Date.now();
    while (Date.now() - startWait < 60000){
      const uEl = document.getElementById('accUser');
      const pEl = document.getElementById('accPass');
      accUser = uEl ? (uEl.value || uEl.textContent || '').toString().trim() : null;
      accPass = pEl ? (pEl.value || pEl.textContent || '').toString().trim() : null;
      if (accUser || accPass) break;
      await wait(500);
    }
    // Inject a hidden pre element with machine-readable JSON so returned HTML contains creds
    const pre = document.createElement('pre');
    pre.id = 'oxylabs-extracted';
    pre.style.display = 'none';
    pre.textContent = JSON.stringify({ accUser: accUser || null, accPass: accPass || null, url: location.href });
    document.body.appendChild(pre);
  } catch(e){
    try { const pre = document.createElement('pre'); pre.id='oxylabs-extracted'; pre.style.display='none'; pre.textContent = JSON.stringify({error: String(e), url: location.href}); document.body.appendChild(pre); } catch(_) {}
  }
})();
'''

# Logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("update_credentials")


def save_debug_html(content: Any, note: Optional[str] = None) -> None:
    """
    Save content to DEBUG_HTML. Accepts strings or objects (stringify safely).
    """
    try:
        if not isinstance(content, str):
            try:
                content = json.dumps(content, ensure_ascii=False, indent=2)
            except Exception:
                content = str(content)
        with open(DEBUG_HTML, "w", encoding="utf-8") as fh:
            if note:
                fh.write("<!-- NOTE: " + str(note).replace("--", "") + " -->\n")
            fh.write(content)
        log.info("Saved debug HTML to %s (len=%d)", DEBUG_HTML, len(content))
    except Exception:
        log.exception("Failed to save debug HTML")


def looks_like_credentials(u: str, p: str) -> bool:
    """
    Return True only if both are digit-only strings and length >= MIN_DIGITS
    """
    if not u or not p:
        return False
    return bool(re.fullmatch(r"\d{" + str(MIN_DIGITS) + r",}", u) and re.fullmatch(r"\d{" + str(MIN_DIGITS) + r",}", p))


def extract_from_injected_pre(html: str) -> Tuple[Optional[str], Optional[str]]:
    """Parse pre#oxylabs-extracted injected by render_script (preferred)."""
    try:
        soup = BeautifulSoup(html, "lxml")
        pre = soup.find("pre", id="oxylabs-extracted")
        if pre:
            try:
                data = json.loads(pre.get_text())
                u = data.get("accUser")
                p = data.get("accPass")
                log.debug("Injected pre content: %s", json.dumps(data)[:200])
                return u, p
            except Exception:
                log.debug("Failed parsing injected pre JSON", exc_info=True)
    except Exception:
        log.debug("Injected pre check failed", exc_info=True)
    return None, None


def extract_from_dom_ids(html: str) -> Tuple[Optional[str], Optional[str]]:
    """Look for elements with id=accUser / id=accPass in the rendered HTML."""
    try:
        soup = BeautifulSoup(html, "lxml")
        ue = soup.find(id="accUser")
        pe = soup.find(id="accPass")
        if ue and pe:
            u = (ue.get("value") or ue.get_text(strip=True) or "").strip()
            p = (pe.get("value") or pe.get_text(strip=True) or "").strip()
            log.debug("DOM id extraction returned: %r / %r", u[:60], p[:60])
            return u, p
    except Exception:
        log.debug("DOM id extraction failed", exc_info=True)
    return None, None


def extract_from_links(html: str) -> Tuple[Optional[str], Optional[str]]:
    """Scan anchor hrefs for ottc.xyz/live/<digits>/<digits> pattern."""
    try:
        soup = BeautifulSoup(html, "lxml")
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if "ottc.xyz" in href and "/live/" in href:
                m = re.search(r'/live/(\d{6,})/(\d{6,})', href)
                if m:
                    u, p = m.group(1), m.group(2)
                    log.info("Found /live/ digits in link: %s -> %s / %s", href[:120], u, p)
                    return u, p
    except Exception:
        log.debug("Link scan failed", exc_info=True)
    return None, None


def call_oxylabs_realtime(retries: int = 3, timeout: int = 180) -> Optional[str]:
    """
    Call Oxylabs Realtime Web Scraper API with the render script, return rendered HTML content.
    """
    if not OXYLABS_USERNAME or not OXYLABS_PASSWORD:
        log.error("OXYLABS_USERNAME and OXYLABS_PASSWORD must be set in environment.")
        return None

    payload = {
        "source": "universal",
        "url": TARGET_URL,
        "render": "html",
        "stealth": True,
        "wait": 60000,  # milliseconds for renderer to wait
        "render_script": RENDER_SCRIPT,
    }

    for attempt in range(1, retries + 1):
        try:
            log.info("Oxylabs realtime attempt %d/%d (wait=%dms)", attempt, retries, payload["wait"])
            r = requests.post(OX_ENDPOINT, auth=(OXYLABS_USERNAME, OXYLABS_PASSWORD), json=payload, timeout=timeout)
            r.raise_for_status()
            data = r.json()
            try:
                content = data["results"][0]["content"]
                if not isinstance(content, str):
                    content = json.dumps(content, ensure_ascii=False)
                return content
            except Exception:
                log.exception("Unexpected response structure from Oxylabs; saving raw response")
                save_debug_html(data, note="oxylabs-raw-response")
                return None
        except requests.RequestException:
            log.exception("Oxylabs request error on attempt %d", attempt)
            if attempt < retries:
                time.sleep(3)
    return None


def update_m3u_file(new_user: str, new_pass: str) -> bool:
    """Replace ottc.xyz/live/<user>/<pass>/ links in languages/lit.m3u with new creds."""
    log.info("Updating %s with new user=%s...", FILE_PATH, new_user[:6])
    try:
        with open(FILE_PATH, "r", encoding="utf-8") as fh:
            content = fh.read()
    except FileNotFoundError:
        log.error("M3U file not found: %s", FILE_PATH)
        return False

    pattern = re.compile(
        r'(https?://[^/\s]*ottc\.xyz(?::\d+)?/live/)([^/]+)/([^/\s]+)(/[^ \n"\']*)?',
        flags=re.IGNORECASE,
    )

    def repl(m):
        prefix = m.group(1)
        suffix = m.group(4) or ""
        return f"{prefix}{new_user}/{new_pass}{suffix}"

    new_content, count = pattern.subn(repl, content)
    if count == 0:
        log.warning("No ottc.xyz/live links found to update.")
        return False

    with open(FILE_PATH, "w", encoding="utf-8") as fh:
        fh.write(new_content)
    log.info("Updated %d link(s) in %s", count, FILE_PATH)
    return True


def main():
    try:
        html = call_oxylabs_realtime(retries=3, timeout=180)
        if not html:
            log.error("Oxylabs rendering failed; check credentials and logs.")
            sys.exit(1)

        save_debug_html(html, note="rendered-html")

        # 1) Prefer injected JSON pre
        u, p = extract_from_injected_pre(html)
        if u and p:
            log.info("Got credentials from injected JSON pre.")
        else:
            # 2) Try DOM ids
            u, p = extract_from_dom_ids(html)
            if u and p:
                log.info("Got credentials from DOM id elements.")
            else:
                # 3) Try explicit ottc.xyz/live/ links
                u, p = extract_from_links(html)
                if u and p:
                    log.info("Got credentials from ottc.xyz/live/ link.")
                else:
                    # No safe source found -> abort
                    log.error("No safe credential source found (injected JSON, DOM ids, or ottc.xyz/live links). Aborting without updating M3U.")
                    sys.exit(1)

        log.info("Candidate credentials (masked): user=%s... pass=%s...", str(u)[:6], str(p)[:6])

        if not looks_like_credentials(u, p):
            log.error("Candidate credentials failed strict validation (digits length >= %d). Aborting.", MIN_DIGITS)
            sys.exit(1)

        if not update_m3u_file(u, p):
            log.error("Failed to update M3U file with validated credentials.")
            sys.exit(1)

        log.info("M3U updated successfully.")
        sys.exit(0)

    except Exception:
        log.exception("Unhandled error")
        sys.exit(1)


if __name__ == "__main__":
    main()