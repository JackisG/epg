"""
update_credentials.py

- Uses Playwright to open the target page, click "Create free IPTV account",
  wait for Cloudflare/Turnstile to finish and the account fields to populate,
  and updates languages/lit.m3u with the new credentials.

- Saves debug_output.html and prints verbose logs for diagnostics.
- Additional XHR & rendered-HTML scanning to capture credentials inserted in non-standard ways.
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

# Logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("update_credentials")

OXYLABS_USERNAME = os.environ.get("OXYLABS_USERNAME")
OXYLABS_PASSWORD = os.environ.get("OXYLABS_PASSWORD")


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
    Heuristic: valid credentials are numeric sequences (observed on site),
    with reasonable length. Return True only for digit-only strings length >= 6.
    """
    if not u or not p:
        return False
    if re.fullmatch(r"\d{6,}", u) and re.fullmatch(r"\d{6,}", p):
        return True
    return False


def extract_from_html_fallback(html: str):
    """
    Try several ways to extract credentials from HTML:
      1) direct elements with id="accUser" and id="accPass"
      2) input[name=...] fallback
      3) look for /live/<digits>/<digits> occurrences
      4) scan for long digit sequences anywhere in the page (first two)
      5) scan anchor hrefs for ottc.xyz/live/<digits>/<digits>
    Returns (user, pass) or (None, None)
    """
    soup = BeautifulSoup(html, "lxml")

    # 1) By id
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
                log.info("Found #accUser/#accPass but they don't look like numeric credentials")
    except Exception:
        log.debug("ID extraction failed", exc_info=True)

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
            else:
                log.info("Found input[name=...] but they don't look numeric")
    except Exception:
        log.debug("Named input extraction failed", exc_info=True)

    # 3) Look for /live/<digits>/<digits> in the rendered HTML
    m = re.search(r'/live/(\d{6,})/(\d{6,})', html)
    if m:
        u = m.group(1)
        p = m.group(2)
        log.info("Found /live/<digits>/<digits> in HTML: %s / %s", u, p)
        if looks_like_credentials(u, p):
            return u, p

    # 4) Find any long digit sequences on the page, return first two
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
                    u = m.group(1)
                    p = m.group(2)
                    log.info("Found credentials in href %s -> %s / %s", href[:150], u, p)
                    if looks_like_credentials(u, p):
                        return u, p
    except Exception:
        log.debug("Link scanning failed", exc_info=True)

    return None, None


def update_m3u_file(new_user: str, new_pass: str) -> bool:
    """
    Replace credentials inside languages/lit.m3u for freeiptv-style URLs.
    Returns True if file updated.
    """
    log.info("Updating %s with new credentials", FILE_PATH)
    try:
        with open(FILE_PATH, "r", encoding="utf-8") as fh:
            txt = fh.read()
    except FileNotFoundError:
        log.error("File not found: %s", FILE_PATH)
        return False

    # Strict pattern: require 'ottc.xyz' in host to avoid matching unrelated CDN links
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


def fetch_credentials_with_playwright(url: str, max_wait_seconds: int = 180):
    """
    Use Playwright to render the page, click the create button and wait for accUser/accPass.
    Returns (user, pass) or (None, None).
    """
    try:
        from playwright.sync_api import sync_playwright, TimeoutError as PWTimeoutError
    except Exception:
        log.exception("Playwright not available (is it installed?)")
        return None, None

    log.info("Starting Playwright for %s", url)
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
                log.warning("page.goto timed out after 120s; saving partial HTML and continuing to interact")
                try:
                    save_debug_html(page.content(), note="partial after goto timeout")
                except Exception:
                    log.debug("Could not save partial HTML after goto timeout", exc_info=True)

            # selectors for the create control - exact text + alternatives
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
                        log.info("Found create control with selector: %s", sel)
                        try:
                            locator.first.scroll_into_view_if_needed(timeout=3000)
                        except Exception:
                            pass
                        try:
                            # force click to ensure the action runs even if element is disabled/overlapped
                            locator.first.click(timeout=10000, force=True)
                            clicked = True
                            log.info("Clicked create control via selector %s (force=True)", sel)
                            break
                        except Exception as e:
                            log.debug("Click attempt failed for %s: %s", sel, e)
                except Exception:
                    log.debug("Error checking selector %s", sel, exc_info=True)

            if not clicked:
                # fallback JS click using a single-line JS string to avoid Python string delimiting issues
                try:
                    js = "const btn = Array.from(document.querySelectorAll('button,a')).find(el => /create\\s+free\\s*iptv/i.test(el.textContent)); if (btn) { btn.scrollIntoView(); btn.click(); return true; } return false;"
                    js_clicked = page.evaluate(js)
                    log.info("Attempted JS click, result: %s", js_clicked)
                except Exception:
                    log.debug("JS click attempt failed", exc_info=True)

            # Also listen for XHR responses that may include credentials in their body/JSON
            xhr_candidates = []

            def on_response(resp):
                try:
                    u = resp.url
                    if "live" in u or "create" in u or "account" in u or "generate" in u:
                        try:
                            txt = resp.text()
                            if txt and re.search(r'\d{6,}', txt):
                                x = txt[:1000]
                                log.info("Captured XHR candidate response from %s", resp.url)
                                xhr_candidates.append((resp.url, txt))
                                # Save the candidate body for debugging
                                save_debug_html(txt, note=f"xhr-candidate from {resp.url}")
                        except Exception:
                            pass
                except Exception:
                    pass

            page.on("response", on_response)

            # After clicking (or JS click), wait for account info: prefer DOM inputs, else scan HTML, else XHR results
            deadline = time.time() + max_wait_seconds
            while time.time() < deadline:
                try:
                    # 1) DOM inputs
                    user_exists = page.locator("#accUser").count() > 0
                    pass_exists = page.locator("#accPass").count() > 0

                    u_val = None
                    p_val = None
                    if user_exists:
                        try:
                            ue = page.locator("#accUser").first
                            u_val = ue.get_attribute("value") or (ue.input_value() if hasattr(ue, "input_value") else None) or ue.inner_text() or None
                        except Exception:
                            try:
                                u_val = page.eval_on_selector("#accUser", "el => el.value || el.innerText || ''")
                            except Exception:
                                u_val = None
                    if pass_exists:
                        try:
                            pe = page.locator("#accPass").first
                            p_val = pe.get_attribute("value") or (pe.input_value() if hasattr(pe, "input_value") else None) or pe.inner_text() or None
                        except Exception:
                            try:
                                p_val = page.eval_on_selector("#accPass", "el => el.value || el.innerText || ''")
                            except Exception:
                                p_val = None

                    if u_val and p_val:
                        u_val = u_val.strip()
                        p_val = p_val.strip()
                        log.info("Credentials found in DOM; raw user=%r pass=%r", u_val[:50], p_val[:50])
                        if looks_like_credentials(u_val, p_val):
                            html = page.content()
                            save_debug_html(html, note="success: credentials found in DOM")
                            return u_val, p_val
                        else:
                            log.warning("DOM credentials do not match numeric pattern; continuing to wait")

                    # 2) Check XHR candidate responses captured
                    for (url, body) in xhr_candidates:
                        u2, p2 = extract_from_html_fallback(body)
                        if u2 and p2:
                            log.info("Extracted credentials from XHR response %s: %s / %s", url, u2, p2)
                            save_debug_html(body, note=f"credentials-from-xhr:{url}")
                            if looks_like_credentials(u2, p2):
                                return u2, p2

                    # 3) Scan rendered page content for long digit sequences
                    html = page.content()
                    u3, p3 = extract_from_html_fallback(html)
                    if u3 and p3:
                        log.info("Extracted credentials via fallback on rendered HTML: %s / %s", u3, p3)
                        save_debug_html(html, note="credentials-from-rendered-html")
                        if looks_like_credentials(u3, p3):
                            return u3, p3

                except Exception:
                    log.debug("Exception inside wait loop; will retry", exc_info=True)

                time.sleep(2)

            # timed out waiting for credentials
            try:
                html = page.content()
                save_debug_html(html, note="timeout: credentials not found within wait period")
            except Exception:
                log.debug("Could not read content when timing out", exc_info=True)

            log.error("Timed out waiting for credentials after %s seconds", max_wait_seconds)
            return None, None

    except Exception:
        log.exception("Playwright flow failed")
        return None, None


def get_credentials():
    # Try Playwright (local rendering) first — best chance to pass Turnstile if it can be solved
    u, p = fetch_credentials_with_playwright(TARGET_URL, max_wait_seconds=180)
    if u and p:
        return u, p

    # Optional Oxylabs fallback (if you have credentials and want to use their rendering service)
    if OXYLABS_USERNAME and OXYLABS_PASSWORD:
        log.info("Attempting Oxylabs realtime API fallback")
        try:
            import requests
            payload = {"source": "universal", "url": TARGET_URL, "render": "html", "stealth": True, "wait": 15000}
            resp = requests.post("https://realtime.oxylabs.io/v1/queries", auth=(OXYLABS_USERNAME, OXYLABS_PASSWORD), json=payload, timeout=120)
            resp.raise_for_status()
            data = resp.json()
            content = None
            try:
                content = data["results"][0]["content"]
            except Exception:
                content = None
            if content:
                save_debug_html(content, note="oxylabs fallback content")
                u2, p2 = extract_from_html_fallback(content)
                if u2 and p2:
                    return u2, p2
                else:
                    log.error("Oxylabs returned content but credentials not found")
        except Exception:
            log.exception("Oxylabs fallback failed")

    # Final direct GET fallback (may be blocked by Cloudflare)
    try:
        import requests
        log.info("Final fallback: plain GET")
        r = requests.get(TARGET_URL, timeout=30, headers={"User-Agent": "Mozilla/5.0"})
        if r.status_code == 200 and r.text:
            save_debug_html(r.text, note="final-get fallback")
            u3, p3 = extract_from_html_fallback(r.text)
            if u3 and p3:
                return u3, p3
    except Exception:
        log.debug("Direct GET fallback failed", exc_info=True)

    log.error("All extraction attempts failed")
    return None, None


def main():
    try:
        user, pwd = get_credentials()
        if not user or not pwd:
            log.error("Could not obtain credentials. Check debug_output.html artifact.")
            sys.exit(1)

        # Final validation before updating: ensure values look numeric
        if not looks_like_credentials(user, pwd):
            log.error("Extracted credentials do not look like expected numeric credentials: %r / %r", user, pwd)
            try:
                save_debug_html(open(DEBUG_HTML, "r", encoding="utf-8").read() if os.path.exists(DEBUG_HTML) else "", note="invalid-extracted-credentials")
            except Exception:
                pass
            sys.exit(1)

        ok = update_m3u_file(user, pwd)
        if not ok:
            log.error("Failed to update m3u file.")
            sys.exit(1)

        log.info("Success: file updated. (user masked in logs)")
        sys.exit(0)

    except Exception:
        log.exception("Unhandled error")
        sys.exit(1)


if __name__ == "__main__":
    main()