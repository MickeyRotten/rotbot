# oauth.py

"""
oauth.py
• Handles FIRST-TIME OAuth flow for *streamer* account
• Handles synchronous token refresh at launch for streamer
• Provides a callable to refresh the bot’s IRC token at launch
Now uses .env for all secrets. Only streamer tokens & channel are stored in config.json.
"""

from __future__ import annotations
import http.server
import socketserver
import threading
import webbrowser
import requests
import time
import json
import asyncio
import os
from urllib.parse import urlparse, parse_qs, quote_plus
from typing import Callable

from twitchAPI.twitch import Twitch
from twitchAPI.type import AuthScope

from dotenv import load_dotenv
load_dotenv()

PORT         = 8765
REDIRECT_URI = f"http://localhost:{PORT}/"

# Load secrets from .env
CLIENT_ID         = os.getenv("CLIENT_ID")
CLIENT_SECRET     = os.getenv("CLIENT_SECRET")
BOT_ACCESS_TOKEN  = os.getenv("BOT_ACCESS_TOKEN")
BOT_REFRESH_TOKEN = os.getenv("BOT_REFRESH_TOKEN")

# --- Helper: Update .env after token refresh ---
def update_env_var(key, value, env_file=".env"):
    import re
    if os.path.exists(env_file):
        with open(env_file, "r") as f:
            lines = f.readlines()
    else:
        lines = []
    found = False
    for i, line in enumerate(lines):
        if re.match(rf"^{re.escape(key)}=", line):
            lines[i] = f"{key}={value}\n"
            found = True
            break
    if not found:
        lines.append(f"{key}={value}\n")
    with open(env_file, "w") as f:
        f.writelines(lines)

def refresh_bot_token_env():
    """Refresh the bot's access token using its refresh token, and update .env."""
    global BOT_ACCESS_TOKEN, BOT_REFRESH_TOKEN
    if not (CLIENT_ID and CLIENT_SECRET and BOT_REFRESH_TOKEN):
        print("[OAuth] Cannot refresh: missing CLIENT_ID, CLIENT_SECRET, or BOT_REFRESH_TOKEN in .env")
        return False
    r = requests.post(
        "https://id.twitch.tv/oauth2/token",
        data={
            "grant_type": "refresh_token",
            "refresh_token": BOT_REFRESH_TOKEN,
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
        }
    )
    if r.status_code != 200:
        print("[OAuth] Refresh failed! Status:", r.status_code, r.text)
        return False
    d = r.json()
    update_env_var("BOT_ACCESS_TOKEN", d["access_token"])
    update_env_var("BOT_REFRESH_TOKEN", d["refresh_token"])
    os.environ["BOT_ACCESS_TOKEN"] = d["access_token"]
    os.environ["BOT_REFRESH_TOKEN"] = d["refresh_token"]
    print("[OAuth] Bot access token refreshed and saved to .env")
    return True

def ensure_valid_bot_token():
    """
    Validate the bot's access token, auto-refresh if needed, and update .env.
    Returns True if valid, False if unable to recover.
    """
    token = os.getenv("BOT_ACCESS_TOKEN")
    r = requests.get(
        "https://id.twitch.tv/oauth2/validate",
        headers={"Authorization": f"OAuth {token}"}
    )
    if r.status_code == 200:
        return True  # Token is valid
    print("[OAuth] Invalid bot access token; attempting to refresh...")
    if refresh_bot_token_env():
        # Re-check after refresh
        token = os.getenv("BOT_ACCESS_TOKEN")
        r = requests.get(
            "https://id.twitch.tv/oauth2/validate",
            headers={"Authorization": f"OAuth {token}"}
        )
        if r.status_code == 200:
            print("[OAuth] Refreshed token is valid!")
            return True
    print("[OAuth] Unable to refresh bot token. Please re-authorize.")
    return False

# -- STREAMER OAUTH & REFRESH -- (UNCHANGED FROM YOURS)

def ensure_streamer_tokens(
    cfg: dict,
    scope_str: str,
    save_cfg: Callable[[dict], None],
):
    if cfg.get("streamer_access_token"):
        return  # already authorised

    box = {}
    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            qs = parse_qs(urlparse(self.path).query)
            if "code" in qs:
                box["code"] = qs["code"][0]
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                self.end_headers()
                self.wfile.write(b"<h1>Streamer authorised! You can close this tab.</h1>")
                threading.Thread(target=svr.shutdown, daemon=True).start()
            else:
                self.send_response(404)
                self.end_headers()
        def log_message(self, *args):
            pass

    svr = socketserver.TCPServer(("localhost", PORT), Handler)
    threading.Thread(target=svr.serve_forever, daemon=True).start()

    auth_url = (
        "https://id.twitch.tv/oauth2/authorize"
        f"?response_type=code"
        f"&client_id={os.getenv('CLIENT_ID')}"
        f"&redirect_uri={quote_plus(REDIRECT_URI)}"
        f"&scope={scope_str}"
    )
    print("[OAuth] Opening browser – log in as the STREAMER and click Authorise")
    webbrowser.open(auth_url)

    while "code" not in box:
        time.sleep(0.1)
    svr.server_close()

    resp = requests.post(
        "https://id.twitch.tv/oauth2/token",
        data={
            "client_id":     os.getenv("CLIENT_ID"),
            "client_secret": os.getenv("CLIENT_SECRET"),
            "code":          box["code"],
            "grant_type":    "authorization_code",
            "redirect_uri":  REDIRECT_URI,
        },
    )
    resp.raise_for_status()
    d = resp.json()
    cfg["streamer_access_token"]  = d["access_token"]
    cfg["streamer_refresh_token"] = d["refresh_token"]

    me = requests.get(
        "https://api.twitch.tv/helix/users",
        headers={
            "Client-ID":     os.getenv("CLIENT_ID"),
            "Authorization": f"Bearer {d['access_token']}"
        },
    ).json()["data"][0]
    cfg["twitch_channel"] = me["login"]

    save_cfg(cfg)
    print("[OAuth] Streamer tokens stored.")

def refresh_streamer_sync(
    cfg: dict,
    save_cfg: Callable[[dict], None],
):
    if not cfg.get("streamer_refresh_token"):
        return

    try:
        resp = requests.post(
            "https://id.twitch.tv/oauth2/token",
            data={
                "client_id":     os.getenv("CLIENT_ID"),
                "client_secret": os.getenv("CLIENT_SECRET"),
                "grant_type":    "refresh_token",
                "refresh_token": cfg["streamer_refresh_token"],
            },
            timeout=10,
        )
        resp.raise_for_status()
        j = resp.json()
        cfg["streamer_access_token"]  = j["access_token"]
        cfg["streamer_refresh_token"] = j["refresh_token"]
        save_cfg(cfg)
        print("[OAuth] Streamer access token refreshed.")
    except Exception as e:
        print("[OAuth] Streamer token refresh failed:", e)
