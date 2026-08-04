import os
import re
import time
import requests
from bs4 import BeautifulSoup

BASE_URL = "https://freeiptv2023-d.ottc.xyz/index.php"
M3U_FILE = "languages/lit.m3u"

API_KEY = os.environ["TWOCAPTCHA_API_KEY"]


session = requests.Session()
session.headers.update({
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 Chrome/138 Safari/537.36"
    )
})


def get_sitekey():
    r = session.get(BASE_URL, timeout=30)
    r.raise_for_status()

    m = re.search(r'sitekey:\s*"([^"]+)"', r.text)
    if not m:
        raise RuntimeError("Unable to locate Turnstile sitekey")

    return m.group(1)


def solve_turnstile(sitekey):
    print("Submitting captcha...")

    r = requests.post(
        "https://2captcha.com/in.php",
        data={
            "key": API_KEY,
            "method": "turnstile",
            "sitekey": sitekey,
            "pageurl": BASE_URL,
            "json": 1,
        },
        timeout=30,
    ).json()

    if r["status"] != 1:
        raise RuntimeError(r)

    captcha_id = r["request"]

    print("Waiting for solution...")

    while True:
        time.sleep(5)

        r = requests.get(
            "https://2captcha.com/res.php",
            params={
                "key": API_KEY,
                "action": "get",
                "id": captcha_id,
                "json": 1,
            },
            timeout=30,
        ).json()

        if r["status"] == 1:
            return r["request"]

        if r["request"] != "CAPCHA_NOT_READY":
            raise RuntimeError(r)


def create_account(token):
    r = session.post(
        BASE_URL,
        data={
            "cf-turnstile-response": token
        },
        allow_redirects=True,
        timeout=60,
    )

    r.raise_for_status()

    soup = BeautifulSoup(r.text, "lxml")

    username = soup.select_one("#accUser")["value"]
    password = soup.select_one("#accPass")["value"]

    return username, password


def update_playlist(username, password):
    with open(M3U_FILE, "r", encoding="utf-8") as f:
        content = f.read()

    new_content = re.sub(
        r"http://freeiptv\.ottc\.xyz:80/live/\d+/\d+/",
        f"http://freeiptv.ottc.xyz:80/live/{username}/{password}/",
        content,
    )

    if new_content == content:
        print("No changes")
        return False

    with open(M3U_FILE, "w", encoding="utf-8") as f:
        f.write(new_content)

    print("Playlist updated")
    return True


def main():
    sitekey = get_sitekey()

    token = solve_turnstile(sitekey)

    username, password = create_account(token)

    print(username)
    print(password)

    update_playlist(username, password)


if __name__ == "__main__":
    main()