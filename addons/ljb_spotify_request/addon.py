"""
ljb_spotify_request
• Channel-point “song request” + !sr command
• Supports YouTube + music.youtube links
• Skips any Spotify track ID present in banned_songs.txt
• Registers EventSub subscription synchronously (no 4003 close)
"""

import os, json, asyncio, logging, re
from pathlib import Path
import yt_dlp, httpx
from twitchAPI.object.eventsub import ChannelPointsCustomRewardRedemptionAddEvent
import threading, socketserver, http.server, time
from urllib.parse import urlparse, parse_qs, quote_plus

ASCII_ART = r"""
 _     _  _      ____ _____  ____  _____  _  ____ __  __
| |__ | || |__  (_ (_`| ()_)/ () \|_   _|| || ===|\ \/ /
|____||_||____|.__)__)|_|   \____/  |_|  |_||__|   |__| 
"""
logging.info(ASCII_ART)

# ── constants ───────────────────────────────────────────────────
CLIENT_ID     = "6c43d2b3ccf544d1b69fa66066ea1b3b"
CLIENT_SECRET = "a53c3033b9084bad974e3090308f5c37"
REDIRECT_URI  = "http://localhost:8765/"
SCOPES        = "user-read-playback-state user-modify-playback-state"
ADDON_NAME    = "ljb_spotify_request"

# Require the streamer token to have this scope:
scopes = ["channel:read:redemptions"]

# ── helper readers ----------------------------------------------------------
def _cfg(folder): return json.load(open(Path(folder)/"addon_config.json", encoding="utf-8"))
def _tok(folder): return json.load(open(Path(folder)/"addon_tokens.json")) if (Path(folder)/"addon_tokens.json").exists() else {}
def _save_tok(folder, d): json.dump(d, open(Path(folder)/"addon_tokens.json","w"), indent=2)

# ── track-ID extraction -----------------------------------------------------
def _track_id(s: str) -> str:
    s = s.strip()
    if s.startswith("spotify:track:"):
        return s.split(":")[-1]
    if "open.spotify.com/track/" in s:
        return s.split("track/")[1].split("?")[0]
    return s

# ── banned list -------------------------------------------------------------
def _load_banned(folder):
    out=set()
    f=Path(folder)/"banned_songs.txt"
    if f.exists():
        for line in f.read_text().splitlines():
            line=line.split("#",1)[0].strip()
            if line: out.add(_track_id(line).lower())
    return out

# ── OAuth helpers -----------------------------------------------------------
def _initial_oauth(folder):
    if (Path(folder)/"addon_tokens.json").exists():
        return
    box={}
    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            q=parse_qs(urlparse(self.path).query)
            if "code" in q:
                box["code"]=q["code"][0]
                self.send_response(200); self.end_headers()
                self.wfile.write(b"<h1>Spotify authorised! You can close this tab.</h1>")
                threading.Thread(target=sv.shutdown,daemon=True).start()
        def log_message(self,*_): pass
    sv=socketserver.TCPServer(("localhost",8765),H)
    threading.Thread(target=sv.serve_forever,daemon=True).start()
    url=("https://accounts.spotify.com/authorize"
         f"?response_type=code&client_id={CLIENT_ID}"
         f"&redirect_uri={quote_plus(REDIRECT_URI)}"
         f"&scope={quote_plus(SCOPES)}")
    print(f"[{ADDON_NAME}] Opening browser for one-time Spotify auth …")
    import webbrowser
    webbrowser.open(url)
    while "code" not in box: time.sleep(.1)
    sv.server_close()
    r=httpx.post("https://accounts.spotify.com/api/token",data={
        "grant_type":"authorization_code","code":box["code"],
        "redirect_uri":REDIRECT_URI,
        "client_id":CLIENT_ID,"client_secret":CLIENT_SECRET})
    r.raise_for_status(); j=r.json()
    _save_tok(folder,{
        "access_token":j["access_token"],
        "refresh_token":j["refresh_token"],
        "expires_at":time.time()+j["expires_in"]
    })

async def _refresh(folder):
    tok=_tok(folder)
    if not tok or time.time()>tok["expires_at"]-60:
        async with httpx.AsyncClient() as cli:
            r=await cli.post("https://accounts.spotify.com/api/token",data={
                "grant_type":"refresh_token",
                "refresh_token":tok["refresh_token"],
                "client_id":CLIENT_ID,
                "client_secret":CLIENT_SECRET})
            r.raise_for_status(); j=r.json()
        tok["access_token"]=j["access_token"]
        tok["expires_at"]=time.time()+j["expires_in"]
        if "refresh_token" in j:
            tok["refresh_token"]=j["refresh_token"]
        _save_tok(folder,tok)
    return tok

# ── regex for all YouTube domains ------------------------------------------
YTLINK = re.compile(r"(https?://)?(www\.)?"
                    r"(youtu\.be/|(?:music\.)?youtube\.com/watch\?v=)",
                    re.I)

# ── main register() ---------------------------------------------------------
def register(bot, folder=os.path.dirname(__file__)):
    cfg   = _cfg(folder)
    banned= _load_banned(folder)
    _initial_oauth(folder)

    async def process_query(query:str, user:str):
        # YouTube link → title
        if YTLINK.search(query):
            url=query.split()[0]
            try:
                info=await asyncio.to_thread(
                    yt_dlp.YoutubeDL({"quiet":True}).extract_info,
                    url, download=False)
                title=re.sub(r"\(.*?official.*?\)", "", info["title"], flags=re.I)
                query=re.sub(r"\[.*?]", "", title).strip()
            except Exception as e:
                await bot.safe_send(cfg["msg_fail"].format(
                    bot_nick=bot.bot_nick,title="YouTube link",artist="",error=str(e), user=user))
                return

        # Reject album / playlist / artist links
        if any(p in query for p in ("open.spotify.com/album/",
                                    "open.spotify.com/playlist/",
                                    "open.spotify.com/artist/",
                                    "spotify:album:", "spotify:playlist:", "spotify:artist:")):
            await bot.safe_send(cfg["msg_fail"].format(
                bot_nick=bot.bot_nick, title="album / playlist",
                artist="", error="only individual tracks can be queued", user=user))
            return

        tok   = await _refresh(folder)
        hdr   = {"Authorization":f"Bearer {tok['access_token']}"}

        async with httpx.AsyncClient() as cli:
            if "open.spotify.com/track/" in query or query.startswith("spotify:track:"):
                r=await cli.get(f"https://api.spotify.com/v1/tracks/{_track_id(query)}",
                                headers=hdr)
                if r.status_code!=200:
                    await bot.safe_send(cfg["msg_fail"].format(
                        bot_nick=bot.bot_nick,title=query,artist="",error=r.text, user=user))
                    return
                tr=r.json()
            else:
                sr=await cli.get("https://api.spotify.com/v1/search",
                                 headers=hdr, params={"q":query,"type":"track","limit":1})
                items=sr.json()['tracks']['items']
                if not items:
                    await bot.safe_send(cfg["msg_fail"].format(
                        bot_nick=bot.bot_nick,title=query,artist="",error="no match", user=user))
                    return
                tr=items[0]

            tid=tr["id"].lower()
            if tid in banned:
                await bot.safe_send(cfg["msg_banned"].format(
                    bot_nick=bot.bot_nick,title=tr["name"],artist=tr["artists"][0]["name"], user=user))
                return

            q=await cli.post("https://api.spotify.com/v1/me/player/queue",
                             headers=hdr, params={"uri":tr["uri"]})
            data = {"bot_nick":bot.bot_nick,
                    "title":tr["name"],
                    "artist":tr["artists"][0]["name"],
                    "error":q.text,
                    "user":user}
            msg = "msg_success" if 200<=q.status_code<300 else "msg_fail"
            await bot.safe_send(cfg[msg].format(**data))

    # channel-point redeem
    async def on_redeem(evt: ChannelPointsCustomRewardRedemptionAddEvent):
        reward_title = None
        try:
            reward_title = evt.event.reward.title
        except AttributeError:
            print("[ERROR] Could not get reward title from event!")
        except Exception as e:
            print(f"[ERROR] Unexpected error reading reward title: {e}")

        if reward_title and reward_title.lower() == cfg["redeem_name"].lower():
            user_input = getattr(evt.event, "user_input", "").strip()
            # Try to get user name (Twitch v5: user_login, Twitch Helix: user_name)
            user = getattr(evt.event, "user_login", None) or getattr(evt.event, "user_name", None) or "someone"
            if user_input:
                await process_query(user_input, user)
            else:
                print("[WARN] No user_input found for this redemption.")

    # !sr command  ────────────────  (mods & streamer only)
    async def cmd_sr(msg, args):
        # permission gate
        author = msg.author
        if not (author.is_mod or author.is_broadcaster):
            await bot.safe_send("Only the streamer or mods can use !sr.")
            return

        if not args:
            await bot.safe_send("Usage: !sr <song or Spotify/YouTube link>")
            return

        user = getattr(msg.author, "display_name", None) or getattr(msg.author, "name", None) or "someone"
        await process_query(" ".join(args), user)

    bot.register("sr", cmd_sr, "queue a song (mods/streamer)")

    # ----- build subscription coroutine, hand it to the bot --------------
    if hasattr(bot.es, "listen_channel_points_custom_reward_redemption_add_v1"):
        sub_coro = bot.es.listen_channel_points_custom_reward_redemption_add_v1(
            broadcaster_user_id=bot.b_id, callback=on_redeem)
    else:
        sub_coro = bot.es.listen_channel_points_custom_reward_redemption_add(
            broadcaster_user_id=bot.b_id, callback=on_redeem)

    # Store coroutine so the core bot can await it synchronously
    bot.pending_subs.append(sub_coro)

    # online message once everything is wired (run after websocket starts)
    async def announce():
        await asyncio.sleep(1)         # give WS a moment
        await bot.safe_send(cfg["msg_online"].format(bot_nick=bot.bot_nick))
    bot.pending_tasks.append(announce())
