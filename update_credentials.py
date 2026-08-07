#!/usr/bin/env python3
"""
update_credentials.py

Uses Oxylabs Realtime Web Scraper API to:
 - open https://freeiptv2023-d.ottc.xyz
 - click "Create free IPTV account"
 - wait for turnstile + page population
 - extract accUser and accPass
 - update languages/lit.m3u with credentials for ottc.xyz/live/... links

Requires OXYLABS_USERNAME and OXYLABS_PASSWORD environment variables.
Saves debug_output.html for diagnostics and logs progress to stdout.
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

# Config
OXYLABS_USERNAME = os.environ.get("OXYLABS_USERNAME")
OXYLABS_PASSWORD = os.environ.get("OXYLABS_PASSWORD")
TARGET_URL = "https://freeiptv2023-d.ottc.xyz"
FILE_PATH = "languages/lit.m3u"
DEBUG_HTML = "debug_output.html"
OX_ENDPOINT = "https://realtime.oxylabs.io/v1/queries"

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
    // Wait up to 40s for values to appear
    let accUser=null, accPass=null;
    const startWait = Date.now();
    while (Date.now() - startWait < 40000){
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
    Heuristic: credentials are digit-only and at least 6 digits (matches site output).
    """
    if not u or not p:
        return False
    return bool(re.fullmatch(r"\d{6,}", u) and re.fullmatch(r"\d{6,}", p))


def extract_from_injected_pre(html: str) -> Tuple[Optional[str], Optional[str]]:
    """If render_script injected a hidden pre#oxylabs-extracted with JSON, parse it first."""
    try:
        soup = BeautifulSoup(html, "lxml")
        pre = soup.find("pre", id="oxylabs-extracted")
        if pre:
            try:
                data = json.loads(pre.get_text())
                u = data.get("accUser")
                p = data.get("accPass")
                return u, p
            except Exception:
                log.debug("Could not parse JSON inside injected pre", exc_info=True)
    except Exception:
        log.debug("Injected pre check failed", exc_info=True)
    return None, None


def fallback_extract_from_html(html: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Other fallbacks:
     - DOM id lookup for accUser/accPass
     - /live/<digits>/<digits> pattern
     - first two long digit sequences on page
    """
    try:
        soup = BeautifulSoup(html, "lxml")
        ue = soup.find(id="accUser")
        pe = soup.find(id="accPass")
        if ue and pe:
            u = (ue.get("value") or ue.get_text(strip=True) or "").strip()
            p = (pe.get("value") or pe.get_text(strip=True) or "").strip()
            if looks_like_credentials(u, p):
                return u, p
    except Exception:
        log.debug("DOM id fallback failed", exc_info=True)

    m = re.search(r'/live/(\d{6,})/(\d{6,})', html)
    if m:
        return m.group(1), m.group(2)

    nums = re.findall(r'\d{6,}', html)
    if len(nums) >= 2:
        return nums[0], nums[1]

    return None, None


def call_oxylabs_realtime(retries: int = 3, timeout: int = 120) -> Optional[str]:
    """
    Call Oxylabs Realtime Web Scraper API with the render script, return rendered HTML content.
    """
    if not OXYLABS_USERNAME or not OXYLABS_PASSWORD:
        log.error("Set OXYLABS_USERNAME and OXYLABS_PASSWORD environment variables.")
        return None

    payload = {
        "source": "universal",
        "url": TARGET_URL,
        "render": "html",
        "stealth": True,
        "wait": 30000,  # milliseconds for renderer to wait
        "render_script": RENDER_SCRIPT,
    }

    for attempt in range(1, retries + 1):
        try:
            log.info("Oxylabs realtime attempt %d/%d", attempt, retries)
            r = requests.post(OX_ENDPOINT, auth=(OXYLABS_USERNAME, OXYLABS_PASSWORD), json=payload, timeout=timeout)
            r.raise_for_status()
            data = r.json()
            # Expect data['results'][0]['content'] to be the rendered HTML
            try:
                content = data["results"][0]["content"]
                # Normalize non-string content
                if not isinstance(content, str):
                    try:
                        content = json.dumps(content, ensure_ascii=False)
                    except Exception:
                        content = str(content)
                return content
            except Exception:
                log.exception("Unexpected Oxylabs response shape; saving raw response")
                save_debug_html(data, note="oxylabs-raw-response")
                return None
        except requests.RequestException:
            log.exception("Oxylabs request failed on attempt %d", attempt)
            if attempt < retries:
                time.sleep(3)
    return None


def update_m3u_file(new_user: str, new_pass: str) -> bool:
    """
    Replace ottc.xyz/live/<user>/<pass>/ links in languages/lit.m3u with new credentials.
    """
    log.info("Updating %s with user=%s...", FILE_PATH, new_user[:6])
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
        html = call_oxylabs_realtime()
        if not html:
            log.error("Oxylabs rendering failed; check logs and API credentials.")
            sys.exit(1)

        # Save raw HTML for debugging
        save_debug_html(html, note="rendered-html")

        # Try injected JSON first
        u, p = extract_from_injected_pre(html)
        if not (u and p):
            # fallback strategies
            u, p = fallback_extract_from_html(html)

        if not (u and p):
            log.error("Could not extract credentials from rendered HTML. See debug_output.html")
            sys.exit(1)

        log.info("Extracted credentials (masked): user=%s..., pass=%s...", str(u)[:6], str(p)[:6])

        if not looks_like_credentials(u, p):
            log.error("Extracted values do not match expected numeric credentials: %r / %r", u, p)
            sys.exit(1)

        ok = update_m3u_file(u, p)
        if not ok:
            log.error("Failed to update the M3U file.")
            sys.exit(1)

        log.info("Successfully updated %s", FILE_PATH)
        sys.exit(0)

    except Exception:
        log.exception("Unhandled error in updater")
        sys.exit(1)


if __name__ == "__main__":
    main()