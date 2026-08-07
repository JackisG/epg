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
            context = browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
            page = context.new_page()

            # Navigate to index.php explicitly (better matches the UI)
            target = url.rstrip("/") + "/index.php"
            log.info("Going to %s", target)
            try:
                # Increase timeout and use networkidle but allow longer wait
                page.goto(target, wait_until="networkidle", timeout=120000)
            except PWTimeoutError:
                log.warning("Page.goto timeout after 120s — saving partial content and continuing.")
                try:
                    html_partial = page.content()
                    save_debug_html(html_partial, note="Partial content after goto timeout")
                except Exception:
                    log.debug("Could not read page content after timeout.", exc_info=True)
                # continue — the page may still load further in background

            # Give Cloudflare time to show challenge; the challenge may present a Turnstile widget.
            # We'll attempt several ways to trigger account creation:
            create_selectors = [
                "text=Create free IPTV account",
                "text=Create Free IPTV Account",
                "text=Create free iptv account",
                "#create-btn",
                "button:has-text(\"Create free IPTV account\")",
                "a:has-text(\"Create free IPTV account\")"
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
                try:
                    js_clicked = page.evaluate("""() => {
                        const btn = Array.from(document.querySelectorAll('button,a')).find(el => /create\\s+free\\s*iptv/i.test(el.textContent));
                        if (btn) { btn.scrollIntoView](#)
