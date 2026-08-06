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
    
    payload = {
        'source': 'universal',
        'url': TARGET_URL,
        'render': 'html',
        'wait_for': '#accUser',  # Wait for the username input to appear on the redirected page
        'timeout': 60000,
        'render_script': '''
            var attempts = 0;
            var interval = setInterval(function() {
                attempts++;
                var btn = document.querySelector('#create-btn');
                if (btn && !btn.disabled) {
                    btn.click();
                    clearInterval(interval);
                } else if (attempts > 10) { // Force click after 5 seconds
                    if (btn) {
                        btn.disabled = false;
                        btn.click();
                        clearInterval(interval);
                    }
                }
            }, 500);
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
    
    try:
        content = data['results'][0]['content']
    except (KeyError, IndexError):
        print("Unexpected Oxylabs response structure:")
        print(data)
        sys.exit(1)

    # Search for the username and password pattern.
    # This regex is much more flexible: it matches id="accUser" followed by value="..." 
    # regardless of attribute order, spaces, or single/double quotes.
    user_match = re.search(r'id=["\']accUser["\'][^>]*value=["\']([^"\']+)["\']', content)
    pass_match = re.search(r'id=["\']accPass["\'][^>]*value=["\']([^"\']+)["\']', content)

    # Fallback regex in case the value attribute comes BEFORE the id attribute
    if not user_match:
        user_match = re.search(r'value=["\']([^"\']+)["\'][^>]*id=["\']accUser["\']', content)
    if not pass_match:
        pass_match = re.search(r'value=["\']([^"\']+)["\'][^>]*id=["\']accPass["\']', content)

    if user_match and pass_match:
        username = user_match.group(1)
        password = pass_match.group(1)
        print(f"Successfully extracted credentials -> User: {username}, Pass: {password}")
        return username, password
    else:
        print("Failed to find credentials in the scraped page content.")
        
        # Save the HTML to a file for the GitHub Action to upload as an artifact
        with open('debug_output.html', 'w', encoding='utf-8') as f:
            f.write(content)
        print("Saved debug HTML to debug_output.html for artifact upload.")
        
        sys.exit(1)

def update_m3u_file(new_username, new_password):
    print(f"Updating file: {FILE_PATH}")
    
    try:
        with open(FILE_PATH, 'r', encoding='utf-8') as f:
            content = f.read()
    except FileNotFoundError:
        print(f"Error: {FILE_PATH} not found in the repository.")
        sys.exit(1)

    pattern = r'(http[s]?://freeiptv\.ottc\.xyz[^ ]*?/live/)\d+/(\d+)(/[^ \"\'\n]*)'
    replacement = rf'\g<1>{new_username}/{new_password}\g<3>'

    new_content, count = re.subn(pattern, replacement, content)

    if count == 0:
        print("WARNING: No links containing 'freeiptv.ottc.xyz' with credentials were found to replace.")
        if "freeiptv.ottc.xyz" in content:
            print("The file contains 'freeiptv.ottc.xyz' but did not match the expected URL structure.")
    else:
        print(f"Successfully updated {count} links.")

    with open(FILE_PATH, 'w', encoding='utf-8') as f:
        f.write(new_content)
        
    print("File successfully saved.")

if __name__ == "__main__":
    if not OXYLABS_USERNAME or not OXYLABS_PASSWORD:
        print("Error: OXYLABS_USERNAME and OXYLABS_PASSWORD environment variables must be set.")
        sys.exit(1)
        
    user, pwd = get_credentials()
    update_m3u_file(user, pwd)