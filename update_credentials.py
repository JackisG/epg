#!/usr/bin/env python3
"""
update_credentials_oxylabs.py

Use Oxylabs Realtime Web Scraper API to render https://freeiptv2023-d.ottc.xyz,
click 'Create free IPTV account', wait for accUser/accPass, extract them and
update languages/lit.m3u.

Set OXYLABS_USERNAME and OXYLABS_PASSWORD in env (or GitHub secrets).
"""

import os
import re
import sys
import time
import json
import logging
from typing import Tuple, Optional
import requests
from bs4 import BeautifulSoup

# Configuration
OXYLABS_USERNAME = os.environ.get("OXYLABS_USERNAME")
OXYLABS_PASSWORD = os.environ.get("OXYLABS_PASSWORD")
TARGET_URL = "https://freeiptv2023-d.ottc.xyz"
FILE_PATH = "languages/lit.m3u"
DEBUG_HTML = "debug_output.html"
OX_ENDPOINT = "https://realtime.oxylabs.io/v1/queries"

# JS render script inserted into the payload (single-line or triple-quoted in Python)
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
      const startEnable = Date.now();
      while (Date.now() - startEnable < 20000){
        try { if (!btn.disabled && !btn.getAttribute('disabled')) break; } catch(e){}
        await wait(500);
      }
      try { btn.click(); } catch(e){
        try { btn.dispatchEvent(new MouseEvent('click', { bubbles: true })); } catch(e){}
      }
    }
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
log = logging.getLogger("oxylabs_updater")


def save_debug_html(html: str, note: Optional[str] = None) -> None:
    try:
        with open(DEBUG_HTML, "w", encoding="utf-8") as fh:
            if note:
                fh.write("<!-- NOTE: " + note.replace("--", "") + " -->\n")
            fh.write(html)
        log.info("Saved debug HTML to %s", DEBUG_HTML)
    except Exception:
        log.exception("Failed to save debug HTML")


def looks_like_credentials(u: str, p: str) -> bool:
    return bool(re.fullmatch(r"\d{6,}", u or "") and re.fullmatch(r"\d{6,}", p or ""))


def parse_extracted_pre(html: str) -> Tuple[Optional[str], Optional[str]]:
    """First try to find the injected pre#oxylabs-extracted JSON."""
    soup = BeautifulSoup(html, "lxml")
    pre = soup.find("pre", id="oxylabs-extracted")
    if pre:
        text = pre.get_text()
        try:
            data = json.loads(text)
            u = data.get("accUser")
            p = data.get("accPass")
            return u, p
        except Exception:
            log.debug("Pre JSON parse failed", exc_info=True)
    return None, None


def fallback_extract_from_html(html: str) -> Tuple[Optional[str], Optional[str]]:
    """Other fallbacks: direct ids, /live/<digits>/<digits> pattern, first two long numbers."""
    soup = BeautifulSoup(html, "lxml")
    try:
        ue = soup.find(id="accUser")
        pe = soup.find(id="accPass")
        if ue and pe:
            u = (ue.get("value") or ue.get_text(strip=True) or "").strip()
            p = (pe.get("value") or pe.get_text(strip=True) or "").strip()
            if looks_like_credentials(u, p): return u, p
    except Exception:
        pass

    m = re.search(r'/live/(\d{6,})/(\d{6,})', html)
    if m:
        return m.group(1), m.group(2)

    nums = re.findall(r'\d{6,}', html)
    if len(nums) >= 2:
        return nums[0], nums[1]

    return None, None


def call_oxylabs_render(retries: int = 3, wait_ms: int = 2000) -> Optional[str]:
    """
    Call Oxylabs Realtime API and return the rendered HTML (results[0].content).
    """
    if not OXYLABS_USERNAME or not OXYLABS_PASSWORD:
        log.error("Set OXYLABS_USERNAME and OXYLABS_PASSWORD environment variables.")
        return None

    payload = {
        "source": "universal",
        "url": TARGET_URL,
        "render": "html",
        "stealth": True,
        "wait": 30000,             # allow up to 30s rendering in Oxylabs
        "render_script": RENDER_SCRIPT
    }

    for attempt in range(1, retries + 1):
        try:
            log.info("Oxylabs render attempt %d/%d", attempt, retries)
            r = requests.post(OX_ENDPOINT, auth=(OXYLABS_USERNAME, OXYLABS_PASSWORD), json=payload, timeout=120)
            r.raise_for_status()
            data = r.json()
            # Extract content
            try:
                content = data["results"][0]["content"]
                # content may be string or object depending on API; ensure string
                if not isinstance(content, str):
                    content = json.dumps(content, ensure_ascii=False)
                return content
            except Exception:
                log.exception("Unexpected Oxylabs response structure; saving raw response")
                save_debug_html(json.dumps(data, ensure_ascii=False, indent=2), note="oxylabs-raw-response")
                return None
        except requests.RequestException:
            log.exception("Oxylabs request failed on attempt %d", attempt)
            if attempt < retries:
                time.sleep(wait_ms / 1000.0)
    return None


def update_m3u_file(new_user: str, new_pass: str) -> bool:
    log.info("Updating %s with new credentials %s / %s", FILE_PATH, new_user[:6], new_pass[:6])
    try:
        with open(FILE_PATH, "r", encoding="utf-8") as fh:
            txt = fh.read()
    except FileNotFoundError:
        log.error("M3U file not found at %s", FILE_PATH)
        return False

    pattern = re.compile(
        r'(https?://[^/\s]*ottc\.xyz(?::\d+)?/live/)([^/]+)/([^/\s]+)(/[^ \n"\']*)?',
        flags=re.IGNORECASE,
    )

    def repl(m):
        prefix = m.group(1)
        suffix = m.group(4) or ""
        return f"{prefix}{new_user}/{new_pass}{suffix}"

    new_txt, count = pattern.subn(repl, txt)
    if count == 0:
        log.warning("No ottc.xyz/live links matched; nothing updated.")
        return False

    with open(FILE_PATH, "w", encoding="utf-8") as fh:
        fh.write(new_txt)
    log.info("Updated %d links in %s", count, FILE_PATH)
    return True


def main():
    # 1) Call Oxylabs render to get final HTML
    html = call_oxylabs_render()
    if not html:
        log.error("Oxylabs rendering failed; check logs and API credentials.")
        sys.exit(1)

    save_debug_html(html, note="rendered-html")

    # 2) Try to parse the injected JSON first
    u, p = parse_extracted_pre(html)
    if not (u and p):
        # fallback parsing
        u, p = fallback_extract_from_html(html)

    if not (u and p):
        log.error("Could not extract credentials from rendered HTML. Check debug_output.html")
        sys.exit(1)

    log.info("Extracted credentials: user=%s pass=%s", u[:6] + "...", p[:6] + "...")

    # 3) Validate credentials
    if not looks_like_credentials(u, p):
        log.error("Extracted values don't match expected numeric credential format.")
        sys.exit(1)

    # 4) Update M3U file
    ok = update_m3u_file(u, p)
    if not ok:
        log.error("Failed to update M3U file.")
        sys.exit(1)

    log.info("M3U file updated successfully.")
    sys.exit(0)


if __name__ == "__main__":
    main()