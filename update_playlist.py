import urllib.request
import os

SOURCE_URL = "https://iptv-org.github.io/iptv/languages/lit.m3u"
DEST_FILE = "languages/lit.m3u"
SEEN_FILE = "seen_channels.txt"

def parse_m3u(content):
    """Extracts channel data, including multi-line tags like EXTVLCOPT."""
    channels = []
    lines = content.strip().split('\n')
    current_tags = []
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
            
        if line.startswith('#'):
            # Collect all # lines (EXTINF, EXTVLCOPT, etc.)
            current_tags.append(line)
        else:
            # It's a URL line. Save the collected tags and the URL.
            if current_tags:
                extinf_block = '\n'.join(current_tags)
                channels.append({'extinf': extinf_block, 'url': line})
                current_tags = []
    return channels

# 1. Fetch Source Playlist
req = urllib.request.Request(SOURCE_URL)
with urllib.request.urlopen(req) as response:
    source_content = response.read().decode('utf-8')
source_channels = parse_m3u(source_content)

# 2. Read Local Seen Channels (The Memory)
seen_urls = set()
if os.path.exists(SEEN_FILE):
    with open(SEEN_FILE, 'r', encoding='utf-8') as f:
        seen_urls = set(line.strip() for line in f if line.strip())

# 3. Handle First Run (Baseline Initialization)
if not seen_urls:
    for c in source_channels:
        seen_urls.add(c['url'])
    with open(SEEN_FILE, 'w', encoding='utf-8') as f:
        for url in sorted(seen_urls):
            f.write(f"{url}\n")
    print("First run: Baseline established. No new channels added to prevent restoring deleted ones.")
    exit(0)

# 4. Find Truly New Channels
new_channels = []
for c in source_channels:
    if c['url'] not in seen_urls:
        new_channels.append(c)
        seen_urls.add(c['url'])

# 5. Append New Channels to Your Playlist
if new_channels:
    # Ensure file ends with newline before appending
    with open(DEST_FILE, 'r', encoding='utf-8') as f:
        content = f.read()
    if content and not content.endswith('\n'):
        with open(DEST_FILE, 'a', encoding='utf-8') as f:
            f.write('\n')
            
    with open(DEST_FILE, 'a', encoding='utf-8') as f:
        for c in new_channels:
            f.write(f"{c['extinf']}\n{c['url']}\n")

    # Update the memory file
    with open(SEEN_FILE, 'w', encoding='utf-8') as f:
        for url in sorted(seen_urls):
            f.write(f"{url}\n")
    print(f"Added {len(new_channels)} new channels.")
else:
    print("No new channels found.")
