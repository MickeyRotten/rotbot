#!/usr/bin/env python3
import json, threading, webbrowser, socketserver, http.server, requests
from urllib.parse import urlparse, parse_qs, quote_plus
import os, sys

# ── CONFIG ─────────────────────────────────────────────────────
CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.json")
REDIRECT_URI = "http://localhost:8765/"

# Load & validate
cfg = json.load(open(CONFIG_PATH))
for key in ("bot_client_id","bot_client_secret"):
    if not cfg.get(key):
        print(f"Missing `{key}` in config.json. Fill that in and retry.")
        sys.exit(1)

# ── TINY HTTP SERVER TO CATCH /?code=… ─────────────────────────
PORT = 8765
class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        qs = parse_qs(urlparse(self.path).query)
        if "code" in qs:
            code = qs["code"][0]
            self.send_response(200)
            self.send_header("Content-Type","text/html")
            self.end_headers()
            self.wfile.write(b"<h1>Bot authorized! You can close this tab.</h1>")
            threading.Thread(target=httpd.shutdown, daemon=True).start()
            # stash the code
            self.server.auth_code = code
        else:
            self.send_response(404)
            self.end_headers()
    def log_message(self, *args): pass

httpd = socketserver.TCPServer(("localhost", PORT), Handler)
threading.Thread(target=httpd.serve_forever, daemon=True).start()

# ── BUILD AND OPEN THE AUTH URL ────────────────────────────────
scopes = "chat:read chat:edit channel:moderate"
params = {
    "response_type": "code",
    "client_id":     cfg["bot_client_id"],
    "redirect_uri":  REDIRECT_URI,
    "scope":         scopes
}
qry = "&".join(f"{k}={quote_plus(v)}" for k,v in params.items())
auth_url = f"https://id.twitch.tv/oauth2/authorize?{qry}"

print("\n1) If your browser didn’t open automatically, paste this URL into it:\n")
print(auth_url + "\n")
webbrowser.open(auth_url)

# ── WAIT FOR THE REDIRECT & SHUTDOWN ────────────────────────────
print("2) Log in as the BOT (liljuicerbot) and click Authorize…")
while not hasattr(httpd, "auth_code"):
    pass
code = httpd.auth_code
httpd.server_close()

# ── EXCHANGE CODE FOR TOKENS ────────────────────────────────────
print("3) Exchanging code for token…")
token_res = requests.post("https://id.twitch.tv/oauth2/token", data={
    "client_id":     cfg["bot_client_id"],
    "client_secret": cfg["bot_client_secret"],
    "code":          code,
    "grant_type":    "authorization_code",
    "redirect_uri":  REDIRECT_URI
})
token_res.raise_for_status()
tok = token_res.json()

# ── WRITE BACK INTO config.json ─────────────────────────────────
cfg["bot_access_token"]  = tok["access_token"]
cfg["bot_refresh_token"] = tok["refresh_token"]
with open(CONFIG_PATH, "w") as f:
    json.dump(cfg, f, indent=2)

print("Bot tokens saved to config.json.")
print("You can now launch the bot with your launch_bot.bat or `python bootstrap.py`.")
