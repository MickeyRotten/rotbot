# twitch_bot.py

from __future__ import annotations

import os
import sys
import json
import asyncio
import time
import logging
import datetime
import signal
from pathlib import Path
from urllib.parse import quote_plus

import requests  # <- needed for token validation
from twitchio.ext import commands
from twitchAPI.twitch import Twitch
from twitchAPI.eventsub.websocket import EventSubWebsocket
from twitchAPI.type import AuthScope
from twitchAPI.helper import first

from .oauth import ensure_streamer_tokens, refresh_streamer_sync
from .oauth import refresh_bot_token
from .rate_limit import Limiter
from .addon_loader import discover

from dotenv import load_dotenv

# ── FILE PATHS & CONFIG ─────────────────────────────────────────
ROOT   = Path(__file__).resolve().parent.parent
CFG_FN = ROOT / "config.json"
ADDONS = ROOT / "addons"
ADDONS.mkdir(parents=True, exist_ok=True)
load_dotenv()

# ── DEFAULT CONFIG ──────────────────────────────────────────────
CLIENT_ID        = os.getenv("CLIENT_ID")
CLIENT_SECRET    = os.getenv("CLIENT_SECRET")
BOT_ACCESS_TOKEN = os.getenv("BOT_ACCESS_TOKEN")
BOT_REFRESH_TOKEN = os.getenv("BOT_REFRESH_TOKEN")

DEFAULT = {
    "streamer_access_token":  None,
    "streamer_refresh_token": None,
    "twitch_channel":         None,
    "bot_nick":               "liljuicerbot"
}

def load_cfg() -> dict:
    """
    Load or create config.json and validate presence of required secrets.
    """
    if not CFG_FN.exists():
        CFG_FN.write_text(json.dumps(DEFAULT, indent=2))
        print(f"Config created at {CFG_FN}. Please fill in twitch_channel & bot_nick.")
        sys.exit(0)

    cfg = json.loads(CFG_FN.read_text())
    for k, v in DEFAULT.items():
        cfg.setdefault(k, v)

    # Check for required secrets in environment
    missing = []
    for var in ["CLIENT_ID", "CLIENT_SECRET", "BOT_ACCESS_TOKEN", "BOT_REFRESH_TOKEN"]:
        if not os.getenv(var):
            missing.append(var)
    if missing:
        print(f"Missing required secret(s) in .env: {', '.join(missing)}. Please fill in and restart.")
        sys.exit(1)

    # Optional: validate token via Twitch API as before, using BOT_ACCESS_TOKEN
    tok = os.getenv("BOT_ACCESS_TOKEN")
    r = requests.get(
        "https://id.twitch.tv/oauth2/validate",
        headers={"Authorization": f"OAuth {tok}"}
    )
    if r.status_code != 200:
        print("Invalid bot access token; please update your .env file.")
        sys.exit(1)

    return cfg

def save_cfg(c: dict):
    CFG_FN.write_text(json.dumps(c, indent=2))


# ── LOGGER ───────────────────────────────────────────────────────
LOG_DIR = ROOT / "logs"
LOG_DIR.mkdir(exist_ok=True)
logfile = LOG_DIR / f"bot_{datetime.date.today()}.txt"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(logfile, encoding="utf-8"),
        logging.StreamHandler()
    ]
)
logging.info("------------- bot starting -------------")


# ── MAIN entrypoint (called by bootstrap.py) ────────────────────
def main():
    cfg = load_cfg()

    # 1) add-on discovery & scope merge
    mods, dirs, extra = discover(ADDONS)
    core = [
        AuthScope.CHAT_READ,
        AuthScope.CHAT_EDIT,
        AuthScope.CHANNEL_READ_REDEMPTIONS
    ]
    all_scopes = sorted({*core, *extra}, key=lambda s: s.value)
    scope_str  = quote_plus(" ".join(s.value for s in all_scopes))

    # 2) ensure streamer token pair (auto-OAuth) & refresh
    ensure_streamer_tokens(cfg, scope_str, save_cfg)
    refresh_streamer_sync(cfg, save_cfg)

    limiter = Limiter()       # 3) message rate limiter

    # ── PRE-LAUNCH BOT TOKEN REFRESH & EVENT LOOP SETUP ───────────
    from .oauth import refresh_bot_token
    refresh_bot_token(cfg, save_cfg)

    # Ensure asyncio.get_event_loop() returns a loop for commands.Bot.__init__()
    import asyncio
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    # 4) twitchIO bot --------------------------------------------------------
    class LJB(commands.Bot):
        def __init__(self):
            # pass the bot_access_token (no "oauth:" in config)
            token = f"oauth:{BOT_ACCESS_TOKEN}"
            super().__init__(
                token=token,
                prefix="!",
                initial_channels=[cfg["twitch_channel"]]
            )
            self.bot_nick      = cfg["bot_nick"]
            self.cmds: dict[str, tuple] = {}
            self.pending_subs  = []
            self.pending_tasks = []
            self.es = None
            self.b_id = None

        async def safe_send(self, txt: str):
            await limiter.wait()
            await self.connected_channels[0].send(txt)

        async def event_ready(self):
            print(f"Connected as {self.bot_nick} in {cfg['twitch_channel']}")
            logging.info("IRC ready; requesting channel JOIN")

            # 0) confirm chat join
            async def _ping():
                try:
                    await self.connected_channels[0].send("i'm alive!")
                    logging.info("Successfully sent 'i'm alive!' to chat")
                except Exception as e:
                    logging.error("JOIN failed: %s", e)
            asyncio.create_task(_ping())

            # 1) Helix / IDs (streamer token)
            twitch = await Twitch(CLIENT_ID, CLIENT_SECRET)
            await twitch.set_user_authentication(
                cfg["streamer_access_token"],
                all_scopes,
                cfg["streamer_refresh_token"]
            )
            self.t_api = twitch
            self.b_id = (await first(
                twitch.get_users(logins=[cfg["twitch_channel"]])
            )).id

            # 2) websocket (created but not started yet)
            self.es = EventSubWebsocket(twitch)

            # 3) START the websocket first
            self.es.start()
            logging.info("EventSub websocket started")

            # 4) register add-ons
            for mod, folder in zip(mods, dirs):
                if hasattr(mod, "register"):
                    try:
                        mod.register(self, folder)
                    except Exception as e:
                        logging.error("[%s] register %s", mod.__name__, e)
                if hasattr(mod, "start"):
                    try:
                        coro = mod.start(self, folder)
                        if asyncio.iscoroutine(coro):
                            asyncio.create_task(coro)
                    except Exception as e:
                        logging.error("[%s] start %s", mod.__name__, e)

            # wait for subscriptions/tasks if any
            if self.pending_subs:
                await asyncio.gather(*self.pending_subs)
            for task in self.pending_tasks:
                asyncio.create_task(task)

            # 5) resubscribe on reconnect
            async def resub_loop():
                last = getattr(self.es, "_session_id", None)
                while True:
                    await asyncio.sleep(30)
                    cur = getattr(self.es, "_session_id", None)
                    if cur and cur != last:
                        logging.warning("EventSub reconnected (session %s)", cur)
                        last = cur
                        for mod, folder in zip(mods, dirs):
                            if hasattr(mod, "register"):
                                try:
                                    mod.register(self, folder)
                                except Exception as e:
                                    logging.error("[%s] re-reg %s", mod.__name__, e)
            asyncio.create_task(resub_loop())

            # core command
            self.register("lilhelp", self.cmd_help, "List commands")

        async def event_message(self, msg):
            if msg.echo or msg.author.name.lower() == self.bot_nick.lower():
                return
            if not msg.content.startswith("!"):
                return
            cmd, *args = msg.content[1:].split()
            if (entry := self.cmds.get(cmd.lower())):
                func, _ = entry
                try:
                    await func(msg, args)
                except Exception as e:
                    await self.safe_send(f"Error: {e}")

        def register(self, name, func, help_text):
            self.cmds[name.lower()] = (func, help_text)

        async def cmd_help(self, msg, _):
            await self.safe_send("Commands: " + ", ".join(sorted(self.cmds)))

    # graceful Ctrl-C --------------------------------------------------------
    bot = LJB()

    async def _shutdown():
        print("\n[liljuicerbot] Shutting down …")
        try:
            if bot.es:
                await bot.es.stop()
            if hasattr(bot, "t_api"):
                await bot.t_api.close()
        finally:
            await bot.close()

    def _sigint(_sig, _frm):
        if bot.loop.is_running():
            asyncio.run_coroutine_threadsafe(_shutdown(), bot.loop)

    signal.signal(signal.SIGINT, _sigint)

    bot.run()
    print("Good-bye.")
