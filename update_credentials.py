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
    
    # Payload for Oxylabs.
    # wait_for: Tells Oxylabs to wait until #accUser appears before capturing HTML.
    # render_script: Injects a red debug banner to log the button's status, then clicks it.
    payload = {
        'source': 'universal',
        'url': TARGET_URL,
        'render': 'html',
        'wait_for': '#accUser', 
        'render_script': '''
            document.addEventListener('DOMContentLoaded', function() {
                // Create a visible debug banner
                var debugDiv = document.createElement('div');
                debugDiv.id = 'oxylabs-debug';
                debugDiv.style.position = 'fixed';
                debugDiv.style.top = '0';
                debugDiv.style.left = '0';
                debugDiv.style.width = '100%';
                debugDiv.style.padding = '20px';
                debugDiv.style.background = 'red';
                debugDiv.style.color = 'white';
                debugDiv.style.fontSize = '24px';
                debugDiv.style.zIndex = '99999';
                debugDiv.innerHTML = 'OXYLABS DEBUG: Script started. Waiting for button...';
                document.body.appendChild(debugDiv);

                var attempts = 0;
                var interval = setInterval(function() {
                    attempts++;
                    var btn = document.querySelector('#create-btn');
                    if (btn) {
                        if (!btn.disabled) {
                            debugDiv.innerHTML = 'OXYLABS DEBUG: Button enabled! Clicking... (Attempt ' + attempts + ')';
                            btn.click();
                            clearInterval(interval);
                        } else {
                            debugDiv.innerHTML = 'OXYLABS DEBUG: Button found but disabled. (Attempt ' + attempts + ')';
                            // Fallback: force click after 15 seconds in case Turnstile callback fails
                            if (attempts > 30) {
                                debugDiv.innerHTML = 'OXYLABS DEBUG: Button still disabled after 15s. Forcing click!';
                                btn.disabled = false;
                                btn.click();
                                clearInterval(interval);
                            }
                        }
                    } else {
                        debugDiv.innerHTML = 'OXYLABS DEBUG: Button not found. (Attempt ' + attempts + ')';
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
    
    try:
        content = data['results'][0]['content']
    except (KeyError, IndexError):
        print("Unexpected Oxylabs response structure:")
        print(data)
        sys.exit(1)

    # Search for the username and password pattern
    user_match = re.search(r'id="accUser"[^>]*value="([^"]+)"', content)
    pass_match = re.search(r'id="accPass"[^>]*value="([^"]+)"', content)

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