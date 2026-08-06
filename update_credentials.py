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
        'stealth': True,  # <-- ADDED STEALTH MODE TO BYPASS CLOUDFLARE DETECTION
        'wait_for': '#accUser',
        'timeout': 90000,
        'render_script': '''
            var debugDiv = document.createElement('div');
            debugDiv.id = 'oxylabs-debug';
            debugDiv.style.cssText = 'position:fixed;top:0;left:0;width:100%;padding:20px;background:red;color:white;font-size:24px;z-index:99999;';
            debugDiv.innerHTML = 'OXYLABS DEBUG: Script attached.';
            document.body.appendChild(debugDiv);

            var manualRenderTried = false;

            var interval = setInterval(function() {
                var tokenInput = document.querySelector('input[name="cf-turnstile-response"]');
                
                if (tokenInput && tokenInput.value) {
                    debugDiv.innerHTML = 'OXYLABS DEBUG: Token found! Force clicking button...';
                    clearInterval(interval);
                    
                    var btn = document.querySelector('#create-btn');
                    if (btn) {
                        btn.disabled = false; 
                        btn.click();          
                    }
                } else {
                    debugDiv.innerHTML = 'OXYLABS DEBUG: Still waiting for token...';
                    
                    // Fallback: If Cloudflare loaded but didn't render, we force it to render
                    if (!manualRenderTried && typeof turnstile !== 'undefined' && document.querySelector('#freeiptv-turnstile') && document.querySelector('#freeiptv-turnstile').innerHTML === '') {
                        debugDiv.innerHTML = 'OXYLABS DEBUG: Turnstile empty. Forcing manual render...';
                        try {
                            turnstile.render("#freeiptv-turnstile", {
                                sitekey: "0x4AAAAAAA_Qtby-wpbozX7J",
                                callback: function(token) {
                                    document.querySelector("#create-btn").disabled = false;
                                }
                            });
                            manualRenderTried = true;
                            debugDiv.innerHTML = 'OXYLABS DEBUG: Manual render called successfully.';
                        } catch(e) {
                            debugDiv.innerHTML = 'OXYLABS DEBUG: Manual render error: ' + e.message;
                        }
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

    # Bulletproof regex: finds id="accUser" and captures the value inside the adjacent quotes.
    user_match = re.search(r'id=["\']?accUser["\']?[^>]*value=["\']?([^"\'>\s]+)', content, re.IGNORECASE)
    pass_match = re.search(r'id=["\']?accPass["\']?[^>]*value=["\']?([^"\'>\s]+)', content, re.IGNORECASE)

    # Fallback regex in case the value attribute comes BEFORE the id attribute in the HTML
    if not user_match:
        user_match = re.search(r'value=["\']?([^"\'>\s]+)[^>]*id=["\']?accUser["\']?', content, re.IGNORECASE)
    if not pass_match:
        pass_match = re.search(r'value=["\']?([^"\'>\s]+)[^>]*id=["\']?accPass["\']?', content, re.IGNORECASE)

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