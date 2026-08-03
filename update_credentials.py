import os
import re
import time
import subprocess
import requests
import pytz
from datetime import datetime
from bs4 import BeautifulSoup

def check_time():
    """Ensure the script only runs exactly at 5 AM Lithuanian time."""
    if os.getenv('GITHUB_ACTIONS') == 'true':
        vilnius_tz = pytz.timezone('Europe/Vilnius')
        now = datetime.now(vilnius_tz)
        if now.hour != 5:
            print(f"Current time in Vilnius is {now.hour}:{now.minute}. Skipping execution until 5 AM.")
            exit(0)

def solve_turnstile(api_key):
    print("Solving Turnstile captcha with 2captcha...")
    payload = {
        "clientKey": api_key,
        "task": {
            "type": "TurnstileTaskProxyless",
            "websiteURL": "https://freeiptv2023-d.ottc.xyz/index.php",
            "websiteKey": "0x4AAAAAAA_Qtby-wpbozX7J"
        }
    }
    res = requests.post("https://api.2captcha.com/createTask", json=payload, timeout=30).json()
    if "errorId" in res and res["errorId"] != 0:
        raise Exception(f"2captcha createTask error: {res}")
    
    task_id = res["taskId"]
    
    while True:
        time.sleep(5)
        res = requests.post("https://api.2captcha.com/getTaskResult", json={
            "clientKey": api_key,
            "taskId": task_id
        }, timeout=30).json()
        
        if res.get("status") == "processing":
            continue
        elif res.get("status") == "ready":
            print("Captcha solved successfully.")
            return res["solution"]["token"]
        else:
            raise Exception(f"2captcha getTaskResult error: {res}")

def get_credentials(api_key):
    token = solve_turnstile(api_key)
    session = requests.Session()
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36",
        "Referer": "https://freeiptv2023-d.ottc.xyz/index.php"
    }
    
    # Get initial page to establish session/cookies
    session.get("https://freeiptv2023-d.ottc.xyz/index.php", headers=headers, timeout=30)
    
    # Submit the form with the Turnstile token
    data = {
        "cf-turnstile-response": token
    }
    
    print("Submitting form...")
    resp = session.post("https://freeiptv2023-d.ottc.xyz/index.php", data=data, headers=headers, timeout=30)
    html = resp.text
    
    # Extract credentials
    # Look for M3U link pattern: .../live/USER/PASS/... or ...?username=USER&password=PASS...
    m3u_match = re.search(r'freeiptv\.ottc\.xyz[^"\'>\s]*?(?:username=|/live/)(\d+)[^"\'>\s]*?(?:password=|/)(\d+)', html)
    if m3u_match:
        return m3u_match.group(1), m3u_match.group(2)
    
    # Fallback: Look for 10-14 digit numbers in the text
    soup = BeautifulSoup(html, 'html.parser')
    text = soup.get_text()
    nums = re.findall(r'\b\d{10,14}\b', text)
    if len(nums) >= 2:
        return nums[0], nums[1]
        
    raise Exception("Could not extract credentials from the response page.")

def update_m3u_file(username, password):
    print(f"New credentials - Username: {username}, Password: {password}")
    
    m3u_path = "languages/lit.m3u"
    if not os.path.exists(m3u_path):
        raise FileNotFoundError(f"{m3u_path} not found in the repository.")
        
    with open(m3u_path, "r", encoding="utf-8") as f:
        content = f.read()
        
    # Find old credentials
    old_match = re.search(r'freeiptv\.ottc\.xyz[^"\'>\s]*?(?:username=|/live/)(\d+)[^"\'>\s]*?(?:password=|/)(\d+)', content)
    
    if old_match:
        old_user = old_match.group(1)
        old_pass = old_match.group(2)
        print(f"Replacing old credentials - Username: {old_user}, Password: {old_pass}")
        content = content.replace(old_user, username)
        content = content.replace(old_pass, password)
    else:
        # Fallback: find any two 10-14 digit numbers in lines containing freeiptv.ottc.xyz
        lines = content.split('\n')
        for line in lines:
            if 'freeiptv.ottc.xyz' in line:
                nums = re.findall(r'\b\d{10,14}\b', line)
                if len(nums) >= 2:
                    print(f"Replacing fallback credentials - Username: {nums[0]}, Password: {nums[1]}")
                    content = content.replace(nums[0], username)
                    content = content.replace(nums[1], password)
                    break
                    
    with open(m3u_path, "w", encoding="utf-8") as f:
        f.write(content)
        
    print("M3U file updated successfully.")

def commit_and_push():
    print("Committing and pushing changes...")
    subprocess.run(["git", "config", "--global", "user.name", "github-actions[bot]"])
    subprocess.run(["git", "config", "--global", "user.email", "github-actions[bot]@users.noreply.github.com"])
    subprocess.run(["git", "add", "languages/lit.m3u"])
    
    # Check if there are changes to commit
    result = subprocess.run(["git", "diff", "--staged", "--quiet"])
    if result.returncode == 0:
        print("No changes to commit.")
        return
        
    subprocess.run(["git", "commit", "-m", "Update IPTV credentials [skip ci]"])
    
    token = os.getenv("GITHUB_TOKEN")
    repo = os.getenv("GITHUB_REPOSITORY")
    if token and repo:
        remote_url = f"https://x-access-token:{token}@github.com/{repo}.git"
        subprocess.run(["git", "push", remote_url, "HEAD:master"])
        print("Pushed successfully.")
    else:
        print("GITHUB_TOKEN or GITHUB_REPOSITORY not set. Skipping push.")

if __name__ == "__main__":
    try:
        check_time()
        api_key = os.getenv("TWOCAPTCHA_API_KEY")
        if not api_key:
            raise ValueError("TWOCAPTCHA_API_KEY environment variable not set.")
            
        user, passwd = get_credentials(api_key)
        update_m3u_file(user, passwd)
        commit_and_push()
    except Exception as e:
        print(f"Error: {e}")
        exit(1)