#!/usr/bin/env python3
import os
import re
from github import Github
from scrapling.fetchers import StealthyFetcher

# ---------- CONFIG ----------
GITHUB_TOKEN = os.environ["GITHUB_TOKEN"]
REPO_NAME = "JackisG/epg"
FILE_PATH = "languages/lit.m3u"
TARGET_URL = "https://freeiptv2023-d.ottc.xyz/index.php?action=view"
# ---------------------------

def fetch_new_credentials():
    print("🌐 Fetching page with StealthyFetcher (auto-solving Cloudflare)...")
    page = StealthyFetcher.fetch(
        TARGET_URL,
        solve_cloudflare=True,
        headless=True,
        network_idle=True
    )
    if page.status != 200:
        raise Exception(f"Failed to fetch page. Status: {page.status}")
    print("✅ Page fetched successfully!")

    username = page.css("#accUser::attr(value)").get()
    password = page.css("#accPass::attr(value)").get()
    m3u_link = page.css("#m3uLink::attr(value)").get()

    if not username or not password or not m3u_link:
        raise Exception("Could not extract credentials from page.")
    print(f"👤 New Username: {username}")
    print(f"🔑 New Password: {password}")
    return username, password

def update_m3u_file(username, password):
    print("📂 Connecting to GitHub...")
    g = Github(GITHUB_TOKEN)
    repo = g.get_repo(REPO_NAME)

    contents = repo.get_contents(FILE_PATH)
    current_content = contents.decoded_content.decode("utf-8")

    lines = current_content.splitlines()
    updated_lines = []
    replaced_count = 0

    pattern = re.compile(
        r'(http://freeiptv\.ottc\.xyz:[0-9]+/(?:live|get\.php)\?.*?)(username=)\d+(.*?)(password=)\d+(.*)'
    )

    for line in lines:
        match = pattern.search(line)
        if match:
            prefix = match.group(1)
            username_part = match.group(2)
            after_username = match.group(3)
            password_part = match.group(4)
            suffix = match.group(5)
            new_line = f"{prefix}{username_part}{username}{after_username}{password_part}{password}{suffix}"
            updated_lines.append(new_line)
            replaced_count += 1
            print(f"🔄 Replaced credentials in: {line[:80]}...")
        else:
            updated_lines.append(line)

    if replaced_count == 0:
        print("⚠️ No lines with 'freeiptv.ottc.xyz' found. Nothing to update.")
        return

    print(f"✅ Updated {replaced_count} URL(s).")
    new_content = "\n".join(updated_lines)

    repo.update_file(
        path=FILE_PATH,
        message=f"Auto-update credentials: username={username}",
        content=new_content,
        sha=contents.sha,
        branch="master"   # change to "main" if your default branch is main
    )
    print("🚀 Successfully pushed updated file to GitHub!")

def main():
    print("🚀 Starting credential update process...")
    username, password = fetch_new_credentials()
    update_m3u_file(username, password)
    print("✅ All done!")

if __name__ == "__main__":
    main()
