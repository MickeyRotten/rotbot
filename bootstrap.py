#!/usr/bin/env python3
"""
bootstrap.py – single entry-point double-clicked by the streamer.
• Installs any missing PyPI wheels from core AND all addons.
• Then jumps into ljb.twitch_bot.main()
"""

import importlib.util, subprocess, sys, json, os, logging, time, asyncio, threading, socketserver, http.server, webbrowser, requests
from pathlib import Path

ASCII_ART = r"""

 __         __     __           __     __  __     __     ______     ______     ______    
/\ \       /\ \   /\ \         /\ \   /\ \/\ \   /\ \   /\  ___\   /\  ___\   /\  == \   
\ \ \____  \ \ \  \ \ \____   _\_\ \  \ \ \_\ \  \ \ \  \ \ \____  \ \  __\   \ \  __<   
 \ \_____\  \ \_\  \ \_____\ /\_____\  \ \_____\  \ \_\  \ \_____\  \ \_____\  \ \_\ \_\ 
  \/_____/   \/_/   \/_____/ \/_____/   \/_____/   \/_/   \/_____/   \/_____/   \/_/ /_/ 
                                                                                         

liljuicerbot v0.01 ALPHA
made by mickeyrotten

"""
print(ASCII_ART)

ROOT       = Path(__file__).parent
ADDONS_DIR = ROOT / "addons"

# -----------------------------------------------------------------
def ensure_pkgs(pkgs):
    """pip-install any package that cannot be imported."""
    missing = [p for p in pkgs if importlib.util.find_spec(p) is None]
    if not missing:
        return
    print("[bootstrap] Installing:", ", ".join(missing))
    cmd = [sys.executable, "-m", "pip", "install", "--user", *missing]
    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as e:
        print("[bootstrap] pip failed:", e)
        sys.exit(1)

# 1) Core hard-coded requirements
core_reqs = ["twitchio", "twitchAPI", "httpx"]
ensure_pkgs(core_reqs)

# 2) Add-on requirements
addon_reqs = []
if ADDONS_DIR.exists():
    for folder in ADDONS_DIR.iterdir():
        if folder.is_dir() and folder.name.startswith("ljb_"):
            cfg = folder / "addon_config.json"
            if cfg.exists():
                try:
                    data = json.loads(cfg.read_text(encoding="utf-8"))
                    addon_reqs += data.get("requirements", [])
                except Exception as exc:
                    print(f"[bootstrap] Warning: {cfg} unreadable: {exc}")

if addon_reqs:
    ensure_pkgs(sorted(set(addon_reqs)))

# -----------------------------------------------------------------
from ljb.twitch_bot import main
main()
