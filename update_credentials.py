import os
import re
import sys
import requests

# Configuration
OXYLABS_USERNAME = os.environ.get("OXYLABS_USERNAME")
OXYLABS_PASSWORD = os.environ.get("OXYLABS_PASSWORD")
TARGET_URL = "https://freeiptv2023-d.ottc.xyz"
FILE_PATH = "languages/lit.m3u"

def get_credentials():
    print("Fetching credentials via Oxylabs Web Scraper API...")
    
    # Payload for Oxylabs. We use 'render': 'html' to execute JavaScript.
    # We inject a script to click any button (handling the invisible captcha/get link button)
    # and add a wait time to allow the new credentials to load into the DOM.
    payload = {
        'source': 'universal',
        'url': TARGET_URL,
        'render': 'html',
        'wait': 7000,  # Wait 7 seconds after script execution
        'render_script': '''
            document.addEventListener('DOMContentLoaded', function() {
                // Attempt to click button, input submit, or elements with class 'btn'
                var btn = document.querySelector('button, input[type="submit"], .btn, a[href*="freeiptv"]');
                if (btn) {
                    console.log("Clicking button...");
                    btn.click();
                }
            });
        '''
    }

    try:
        response = requests.post(
            'https://realtime.oxylabs.io/v1/queries',
            auth=(OXYLABS_USERNAME, OXYLABS_PASSWORD),
            json=payload,
            timeout=90
        )
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        print(f"Error communicating with Oxylabs: {e}")
        sys.exit(1)

    data = response.json()
    
    # Safely extract HTML content from Oxylabs response
    try:
        content = data['results'][0]['content']
    except (KeyError, IndexError):
        print("Unexpected Oxylabs response structure:")
        print(data)
        sys.exit(1)

    # Search for the username and password pattern in the scraped HTML.
    # Based on your example, we are looking for a pattern like 108465849651/328455351894
    # Adjust the regex if the site formats the credentials differently (e.g. labeled "Username: 123")
    match = re.search(r'(\d{10,15})/(\d{10,15})', content)
    
    # Fallback: if it's not in URL format, look for generic numbers if labeled
    if not match:
        match = re.search(r'Username.*?(\d{10,15}).*?Password.*?(\d{10,15})', content, re.IGNORECASE | re.DOTALL)

    if match:
        username = match.group(1)
        password = match.group(2)
        print(f"Successfully extracted credentials -> User: {username}, Pass: {password}")
        return username, password
    else:
        print("Failed to find credentials in the scraped page content.")
        # Uncomment the next line to debug the HTML returned by Oxylabs in GitHub Actions logs
        # print("HTML CONTENT:\n", content[:2000])
        sys.exit(1)

def update_m3u_file(new_username, new_password):
    print(f"Updating file: {FILE_PATH}")
    
    try:
        with open(FILE_PATH, 'r', encoding='utf-8') as f:
            content = f.read()
    except FileNotFoundError:
        print(f"Error: {FILE_PATH} not found in the repository.")
        sys.exit(1)

    # This regex finds URLs containing freeiptv.ottc.xyz and replaces the old numbers
    # Example: http://freeiptv.ottc.xyz:80/live/OLD_USER/OLD_PASS/47280.ts
    # Group 1: http://freeiptv.ottc.xyz.../live/
    # Group 2: /... (rest of the link like /47280.ts)
    pattern = r'(http[s]?://freeiptv\.ottc\.xyz[^ ]*?/live/)\d+/(\d+)(/[^ \"\'\n]*)'
    replacement = rf'\g<1>{new_username}/{new_password}\g<3>'

    new_content, count = re.subn(pattern, replacement, content)

    if count == 0:
        print("WARNING: No links containing 'freeiptv.ottc.xyz' with credentials were found to replace.")
        # Check if the links just exist without regex matches to avoid empty commits
        if "freeiptv.ottc.xyz" in content:
            print("The file contains 'freeiptv.ottc.xyz' but did not match the expected URL structure.")
    else:
        print(f"Successfully updated {count} links.")

    # Write the updated content back to the file
    with open(FILE_PATH, 'w', encoding='utf-8') as f:
        f.write(new_content)
        
    print("File successfully saved.")

if __name__ == "__main__":
    if not OXYLABS_USERNAME or not OXYLABS_PASSWORD:
        print("Error: OXYLABS_USERNAME and OXYLABS_PASSWORD environment variables must be set.")
        sys.exit(1)
        
    user, pwd = get_credentials()
    update_m3u_file(user, pwd)