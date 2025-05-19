import os, json, asyncio, logging, re
from pathlib import Path
import yt_dlp
from spotipy import Spotify, SpotifyException
from spotipy.oauth2 import SpotifyOAuth
from twitchAPI.object.eventsub import ChannelPointsCustomRewardRedemptionAddEvent
from dotenv import load_dotenv

ASCII_ART = r"""
 _     _  _      ____ _____  ____  _____  _  ____ __  __
| |__ | || |__  (_ (_`| ()_)/ () \|_   _|| || ===|\ \/ /
|____||_||____|.__)__)|_|   \____/  |_|  |_||__|   |__| 
"""
logging.info(ASCII_ART)

# ── constants ───────────────────────────────────────────────────
CLIENT_ID     = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")
REDIRECT_URI  = "http://localhost:8765/"
SCOPES        = "user-read-playback-state user-modify-playback-state"
ADDON_NAME    = "ljb_spotify_request"
ROOT = Path(__file__).resolve().parent.parent  # adjust as needed
load_dotenv(dotenv_path=ROOT / ".env")

def _cfg(folder): return json.load(open(Path(folder)/"addon_config.json", encoding="utf-8"))
def _load_banned(folder):
    out=set()
    f=Path(folder)/"banned_songs.txt"
    if f.exists():
        for line in f.read_text().splitlines():
            line=line.split("#",1)[0].strip()
            if line: out.add(line.lower())
    return out

# ── regex for all YouTube domains ------------------------------------------
YTLINK = re.compile(r"(https?://)?(www\.)?"
                    r"(youtu\.be/|(?:music\.)?youtube\.com/watch\?v=)",
                    re.I)

def register(bot, folder=os.path.dirname(__file__)):
    cfg    = _cfg(folder)
    banned = _load_banned(folder)

    # Initialize Spotipy (creates/refreshes token as needed)
    try:
        sp_oauth = SpotifyOAuth(
            client_id=CLIENT_ID,
            client_secret=CLIENT_SECRET,
            redirect_uri=REDIRECT_URI,
            scope=SCOPES,
            cache_path=str(Path(folder)/".spotify_cache")
        )
        sp = Spotify(auth_manager=sp_oauth)
        logging.info("[Spotify] Spotipy initialized.")
    except Exception as e:
        logging.error(f"[Spotify] Failed to initialize Spotipy: {e}")
        raise

    async def process_query(query: str, user: str):
        # Try to get a track name if it's a YouTube link
        if YTLINK.search(query):
            url = query.split()[0]
            try:
                info = await asyncio.to_thread(
                    yt_dlp.YoutubeDL({"quiet": True}).extract_info,
                    url, download=False)
                title = re.sub(r"\(.*?official.*?\)", "", info["title"], flags=re.I)
                query = re.sub(r"\[.*?]", "", title).strip()
            except Exception as e:
                logging.error(f"[YouTube] Failed to extract title: {e}")
                await bot.safe_send(cfg["msg_fail"].format(
                    bot_nick=bot.bot_nick, title="YouTube link", artist="", error=str(e), user=user))
                return

        # Block album/playlist/artist links
        if any(p in query for p in ("open.spotify.com/album/",
                                    "open.spotify.com/playlist/",
                                    "open.spotify.com/artist/",
                                    "spotify:album:", "spotify:playlist:", "spotify:artist:")):
            await bot.safe_send(cfg["msg_fail"].format(
                bot_nick=bot.bot_nick, title="album / playlist",
                artist="", error="only individual tracks can be queued", user=user))
            return

        try:
            # Search for track by URI or query
            track = None
            if "open.spotify.com/track/" in query or query.startswith("spotify:track:"):
                track_id = query.split("/")[-1].split("?")[0] if "/" in query else query.split(":")[-1]
                try:
                    track = sp.track(track_id)
                except SpotifyException as se:
                    logging.error(f"[Spotify] Track fetch error: {se}")
            else:
                results = sp.search(q=query, type="track", limit=1)
                items = results.get('tracks', {}).get('items', [])
                if items:
                    track = items[0]

            if not track:
                await bot.safe_send(cfg["msg_fail"].format(
                    bot_nick=bot.bot_nick, title=query, artist="", error="no match", user=user))
                return

            tid = track["id"].lower()
            if tid in banned:
                await bot.safe_send(cfg["msg_banned"].format(
                    bot_nick=bot.bot_nick, title=track["name"], artist=track["artists"][0]["name"], user=user))
                return

            # Add to playback queue
            try:
                sp.add_to_queue(track["uri"])
                status = "msg_success"
                error = ""
            except SpotifyException as se:
                status = "msg_fail"
                error = str(se)
                logging.error(f"[Spotify] Add to queue failed: {se}")

            data = {"bot_nick": bot.bot_nick,
                    "title": track["name"],
                    "artist": track["artists"][0]["name"],
                    "error": error,
                    "user": user}
            await bot.safe_send(cfg[status].format(**data))

        except Exception as e:
            logging.error(f"[Spotify] Unexpected error in process_query: {e}")
            await bot.safe_send(cfg["msg_fail"].format(
                bot_nick=bot.bot_nick, title=query, artist="", error=str(e), user=user))

    # Channel point redeem
    async def on_redeem(evt: ChannelPointsCustomRewardRedemptionAddEvent):
        reward_title = None
        try:
            reward_title = evt.event.reward.title
        except AttributeError:
            logging.error("[ERROR] Could not get reward title from event!")
        except Exception as e:
            logging.error(f"[ERROR] Unexpected error reading reward title: {e}")

        if reward_title and reward_title.lower() == cfg["redeem_name"].lower():
            user_input = getattr(evt.event, "user_input", "").strip()
            user_name = getattr(evt.event, "user_name", None) or getattr(evt.event, "user_login", "someone")
            if user_input:
                await process_query(user_input, user_name)
            else:
                logging.warning("[WARN] No user_input found for this redemption.")

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

        await process_query(" ".join(args), msg.author.display_name)

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
