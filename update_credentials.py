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
    # The render_script waits for the Cloudflare Turnstile to enable the button,
    # clicks it, and then we wait 10 seconds for the new page to load.
    payload = {
        'source': 'universal',
        'url': TARGET_URL,
        'render': 'html',
        'wait': 10000,  # Wait 10 seconds after script execution
        'render_script': '''
            document.addEventListener('DOMContentLoaded', function() {
                var interval = setInterval(function() {
                    var btn = document.querySelector('#create-btn');
                    if (btn && !btn.disabled) {
                        btn.click();
                        clearInterval(interval);
                    }
                }, 500);
            });
        '''
    }

    try:
        response = requests.post(
            'https://realtime.oxylabs.io/v1/queries',
            auth=(OXYLABS_USERNAME, OXYLABS_PASSWORD),
            json=payload,
            timeout=120
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
    # Based on your attached file, we are looking for:
    # <input type="text" class="form-control" id="accUser" value="789097059513" readonly="">
    # <input type="text" class="form-control" id="accPass" value="620130485123" readonly="">
    user_match = re.search(r'id="accUser"[^>]*value="([^"]+)"', content)
    pass_match = re.search(r'id="accPass"[^>]*value="([^"]+)"', content)

    if user_match and pass_match:
        username = user_match.group(1)
        password = pass_match.group(1)
        print(f"Successfully extracted credentials -> User: {username}, Pass: {password}")
        return username, password
    else:
        print("Failed to find credentials in the scraped page content.")
        print("Printing HTML content for debugging purposes:\n")
        print("------ START HTML CONTENT ------")
        print(content)
        print("------ END HTML CONTENT ------\n")
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
    pattern = r'(http[s]?://freeiptv\.ottc\.xyz[^ ]*?/live/)\d+/(\d+)(/[^ \"\'\n]*)'
    replacement = rf'\g<1>{new_username}/{new_password}\g<3>'

    new_content, count = re.subn(pattern, replacement, content)

    if count == 0:
        print("WARNING: No links containing 'freeiptv.ottc.xyz' with credentials were found to replace.")
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