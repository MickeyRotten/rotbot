#!/usr/bin/env python3
import threading, webbrowser, socketserver, http.server, requests
from urllib.parse import urlparse, parse_qs, quote_plus
import os, sys
from dotenv import load_dotenv

# ── LOAD SECRETS FROM .env ──────────────────────────────────────
load_dotenv()
CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")
if not CLIENT_ID or not CLIENT_SECRET:
    print("Missing CLIENT_ID or CLIENT_SECRET in .env. Fill that in and retry.")
    sys.exit(1)

REDIRECT_URI = "http://localhost:8765/"
PORT = 8765

# ── TINY HTTP SERVER TO CATCH /?code=… ─────────────────────────
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
    "client_id":     CLIENT_ID,
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
    "client_id":     CLIENT_ID,
    "client_secret": CLIENT_SECRET,
    "code":          code,
    "grant_type":    "authorization_code",
    "redirect_uri":  REDIRECT_URI
})
token_res.raise_for_status()
tok = token_res.json()

# ── WRITE TOKENS TO .env ────────────────────────────────────────
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

update_env_var("BOT_ACCESS_TOKEN", tok["access_token"])
update_env_var("BOT_REFRESH_TOKEN", tok["refresh_token"])

print("Bot tokens saved to .env.")
print("You can now launch the bot with your launch_bot.bat or `python bootstrap.py`.")
