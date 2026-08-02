#!/usr/bin/env python3
import os
import sys
import re
import traceback
import asyncio
from github import Github

# ---------- Dynamically locate cloudflare-solver module ----------
def find_module(base_dir, module_name="cloudflare_solver"):
    """Recursively search for a module folder containing __init__.py."""
    for root, dirs, files in os.walk(base_dir):
        if module_name in dirs:
            potential_path = os.path.join(root, module_name)
            if os.path.isdir(potential_path) and os.path.exists(os.path.join(potential_path, "__init__.py")):
                return os.path.dirname(potential_path)  # parent directory
        # Also check if a .py file with that name exists
        for f in files:
            if f == f"{module_name}.py":
                return root
    return None

base_dir = "./cloudflare-solver"
if not os.path.isdir(base_dir):
    print(f"❌ Directory {base_dir} not found. Ensure it's cloned.")
    sys.exit(1)

module_path = find_module(base_dir)
if module_path:
    sys.path.insert(0, os.path.abspath(module_path))
    print(f"📁 Added to PYTHONPATH: {os.path.abspath(module_path)}")
else:
    print("❌ Could not locate cloudflare_solver module. Dumping directory tree:")
    os.system(f"find {base_dir} -type f -name '*.py' | head -20")
    sys.exit(1)

# Now import
try:
    from cloudflare_solver import CloudflareSolver, ChallengeType
except ImportError as e:
    print("❌ Failed to import cloudflare_solver even after path update.")
    traceback.print_exc()
    sys.exit(1)

# --------------------------------------------------------------

GITHUB_TOKEN = os.environ["GITHUB_TOKEN"]
REPO_NAME = "JackisG/epg"
FILE_PATH = "languages/lit.m3u"
TARGET_URL = "https://freeiptv2023-d.ottc.xyz/index.php?action=view"

async def fetch_new_credentials():
    print("🌐 Launching CloudflareSolver (latest version from GitHub) ...")
    solver = CloudflareSolver(
        challenge_type=ChallengeType.TURNSTILE,
        headless=True,
        os=["windows"]
    )
    page_html = await solver.solve(TARGET_URL)
    if not page_html:
        raise Exception("Failed to solve Cloudflare challenge")

    username_match = re.search(r'id="accUser"\s+value="([^"]+)"', page_html)
    password_match = re.search(r'id="accPass"\s+value="([^"]+)"', page_html)

    if not username_match or not password_match:
        print("⚠️ Could not find credentials in HTML. Snippet:")
        print(page_html[:1000])
        raise Exception("Credentials not found in solved page")

    username = username_match.group(1)
    password = password_match.group(1)
    print(f"👤 Username: {username}")
    print(f"🔑 Password: {password}")
    return username, password

def update_m3u_file(username, password):
    print("📂 Connecting to GitHub...")
    g = Github(GITHUB_TOKEN)
    repo = g.get_repo(REPO_NAME)

    contents = repo.get_contents(FILE_PATH)
    current = contents.decoded_content.decode("utf-8")
    lines = current.splitlines()
    new_lines = []
    replaced = 0

    pattern = re.compile(
        r'(http://freeiptv\.ottc\.xyz:[0-9]+/(?:live|get\.php)\?.*?)(username=)\d+(.*?)(password=)\d+(.*)'
    )

    for line in lines:
        m = pattern.search(line)
        if m:
            new_line = f"{m.group(1)}{m.group(2)}{username}{m.group(3)}{m.group(4)}{password}{m.group(5)}"
            new_lines.append(new_line)
            replaced += 1
            print(f"🔄 Updated: {line[:60]}...")
        else:
            new_lines.append(line)

    if replaced == 0:
        print("⚠️ No 'freeiptv.ottc.xyz' URLs found – nothing changed.")
        return

    repo.update_file(
        path=FILE_PATH,
        message=f"Auto-update credentials: username={username}",
        content="\n".join(new_lines),
        sha=contents.sha,
        branch="master"   # change to "main" if needed
    )
    print(f"✅ Updated {replaced} URL(s) and pushed to GitHub.")

def main():
    try:
        user, pwd = asyncio.run(fetch_new_credentials())
        update_m3u_file(user, pwd)
        print("🎉 All done!")
    except Exception as e:
        print(f"❌ ERROR: {e}")
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
