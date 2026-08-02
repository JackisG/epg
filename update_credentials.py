#!/usr/bin/env python3
import os
import re
import sys
import traceback
import asyncio
from github import Github
from cloudflare_solver import CloudflareSolver, ChallengeType

GITHUB_TOKEN = os.environ["GITHUB_TOKEN"]
REPO_NAME = "JackisG/epg"
FILE_PATH = "languages/lit.m3u"
TARGET_URL = "https://freeiptv2023-d.ottc.xyz/index.php?action=view"

async def fetch_new_credentials():
    print("🌐 Launching CloudflareSolver (latest version, cloned from GitHub) ...")
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
