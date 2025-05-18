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
    """Update or add a key=value pair in the .env file."""
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

# --- OAuth for Streamer ---
def ensure_streamer_tokens(
    cfg: dict,
    scope_str: str,
    save_cfg: Callable[[dict], None],
):
    """
    If cfg already contains streamer_access_token → no-op.
    Otherwise runs the browser consent flow and fills into cfg:
        - streamer_access_token
        - streamer_refresh_token
        - twitch_channel          (login of the user who authorised)
    Then calls save_cfg(cfg).
    Uses CLIENT_ID, CLIENT_SECRET from .env
    """
    if cfg.get("streamer_access_token"):
        return  # already authorised

    # mini localhost server to catch "?code="
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
        f"&client_id={CLIENT_ID}"
        f"&redirect_uri={quote_plus(REDIRECT_URI)}"
        f"&scope={scope_str}"
    )
    print("[OAuth] Opening browser – log in as the STREAMER and click Authorise")
    webbrowser.open(auth_url)

    # wait for code
    while "code" not in box:
        time.sleep(0.1)
    svr.server_close()

    # exchange for tokens
    resp = requests.post(
        "https://id.twitch.tv/oauth2/token",
        data={
            "client_id":     CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "code":          box["code"],
            "grant_type":    "authorization_code",
            "redirect_uri":  REDIRECT_URI,
        },
    )
    resp.raise_for_status()
    d = resp.json()
    cfg["streamer_access_token"]  = d["access_token"]
    cfg["streamer_refresh_token"] = d["refresh_token"]

    # fetch the streamer’s login
    me = requests.get(
        "https://api.twitch.tv/helix/users",
        headers={
            "Client-ID":     CLIENT_ID,
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
    """
    Refreshes cfg['streamer_access_token'] via cfg['streamer_refresh_token'].
    No-op if no streamer_refresh_token in cfg.
    Uses CLIENT_ID, CLIENT_SECRET from .env
    """
    if not cfg.get("streamer_refresh_token"):
        return

    try:
        resp = requests.post(
            "https://id.twitch.tv/oauth2/token",
            data={
                "client_id":     CLIENT_ID,
                "client_secret": CLIENT_SECRET,
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


async def _do_refresh_bot():
    """
    Async helper to refresh the bot’s own IRC token.
    Uses CLIENT_ID, CLIENT_SECRET, BOT_ACCESS_TOKEN, BOT_REFRESH_TOKEN from .env.
    Saves new tokens back to .env!
    """
    cli = await Twitch(CLIENT_ID, CLIENT_SECRET)
    await cli.set_user_authentication(
        BOT_ACCESS_TOKEN,
        [AuthScope.CHAT_READ, AuthScope.CHAT_EDIT],
        BOT_REFRESH_TOKEN,
    )
    new = await cli.refresh_user_token()
    await cli.close()
    # persist new bot tokens to .env
    update_env_var("BOT_ACCESS_TOKEN", new["access_token"])
    update_env_var("BOT_REFRESH_TOKEN", new["refresh_token"])
    print("[OAuth] Bot token refreshed.")


def refresh_bot_token():
    """
    Refresh the bot's IRC token using its refresh_token, synchronously.
    Uses CLIENT_ID, CLIENT_SECRET, BOT_REFRESH_TOKEN from .env.
    Saves new tokens back to .env!
    """
    if not BOT_REFRESH_TOKEN:
        return

    try:
        r = requests.post(
            "https://id.twitch.tv/oauth2/token",
            data={
                "grant_type":    "refresh_token",
                "refresh_token": BOT_REFRESH_TOKEN,
                "client_id":     CLIENT_ID,
                "client_secret": CLIENT_SECRET,
            },
            timeout=10
        )
        r.raise_for_status()
        j = r.json()
        update_env_var("BOT_ACCESS_TOKEN", j["access_token"])
        update_env_var("BOT_REFRESH_TOKEN", j["refresh_token"])
        print("[OAuth] Bot access token refreshed.")
    except Exception as e:
        print(f"[OAuth] Bot token auto-refresh failed: {e}")
