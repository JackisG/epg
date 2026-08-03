import asyncio
import json
import re
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup

async def get_iptv_credentials():
    async with async_playwright() as p:
        # Launch headless browser
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        
        url = "https://freeiptv2023-d.ottc.xyz/index.php"
        print(f"[*] Navigating to {url}")
        await page.goto(url, wait_until="domcontentloaded")
        
        print("[*] Waiting for Cloudflare Turnstile to verify and unlock the button...")
        try:
            # The site's JS enables the button once Turnstile passes: document.querySelector("#create-btn").disabled = false;
            await page.wait_for_function("document.querySelector('#create-btn').disabled === false", timeout=90000)
        except Exception as e:
            print("[!] Timeout: Turnstile verification failed. Headless browsers are often blocked by Turnstile.")
            await browser.close()
            raise e
            
        print("[*] Button unlocked. Submitting form...")
        await page.click("#create-btn")
        
        print("[*] Waiting for navigation to credentials page...")
        await page.wait_for_url("**/index.php?action=view**", timeout=30000)
        
        content = await page.content()
        soup = BeautifulSoup(content, "html.parser")
        
        # Extract data 
        page_text = soup.get_text(" ", strip=True)
        credentials = {
            "server_url": "",
            "username": "",
            "password": "",
            "m3u_link": "",
            "activation": "",
            "expiration": ""
        }
        
        # Example extraction logic (Adjust selectors based on the exact DOM of the view page)
        url_match = re.search(r"(http[s]?://[^\s]+\.m3u[^\s]*)", page_text)
        if url_match:
            credentials["m3u_link"] = url_match.group(1)
            
        # TODO: Add specific BeautifulSoup selectors here to map Server URL, Username, Password, etc.
        # Example: 
        # for row in soup.find_all('tr'):
        #     if 'IPTV Username' in row.text: credentials['username'] = row.find('td').text.strip()
        
        print("[*] Credentials extracted successfully.")
        
        # Save to JSON file for repository storage
        with open("credentials.json", "w") as f:
            json.dump(credentials, f, indent=4)
            
        # Export to GitHub Actions outputs (Legacy syntax, adjust to $GITHUB_OUTPUT if needed)
        print(f"::set-output name=m3u_link::{credentials['m3u_link']}")
        
        await browser.close()

if __name__ == "__main__":
    asyncio.run(get_iptv_credentials())