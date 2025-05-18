#!/usr/bin/env python3
"""
bootstrap.py – single entry-point double-clicked by the streamer.
• Installs any missing PyPI wheels from core AND all addons.
• Checks for updates (and applies them if the user accepts).
• Then jumps into ljb.twitch_bot.main()
"""

import importlib.util
import subprocess
import sys
import json
import os
import logging
import time
import asyncio
import threading
import socketserver
import http.server
import webbrowser
import requests
import dotenv
from pathlib import Path

ASCII_ART = r"""

 __         __     __           __     __  __     __     ______     ______     ______    
/\ \       /\ \   /\ \         /\ \   /\ \/\ \   /\ \   /\  ___\   /\  ___\   /\  == \   
\ \ \____  \ \ \  \ \ \____   _\_\ \  \ \ \_\ \  \ \ \  \ \ \____  \ \  __\   \ \  __<   
 \ \_____\  \ \_\  \ \_____\ /\_____\  \ \_____\  \ \_\  \ \_____\  \ \_____\  \ \_\ \_\ 
  \/_____/   \/_/   \/_____/ \/_____/   \/_____/   \/_/   \/_____/   \/_____/   \/_/ /_/ 
                                                                                        
"""
print(ASCII_ART)

# Load version number from version.txt
version_file = Path(__file__).parent / "version.txt"
if version_file.exists():
    with open(version_file, "r", encoding="utf-8") as f:
        VERSION = f.read().strip()
else:
    VERSION = "unknown"

print(f"version: {VERSION}")

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
core_reqs = [
    "twitchio",
    "twitchAPI",
    "httpx",
    "requests",     # for update_checker and token validation
    "zipfile36",    # fallback for zipfile on older Python (optional, but safe)
    "python-dotenv" # for .env support
]
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

# 3) Update checker requirements (ensure any missing deps for updater)
update_reqs = [
    "requests",  # already listed above, but harmless to repeat
]
ensure_pkgs(update_reqs)

# -----------------------------------------------------------------
# 4) Check for updates before running bot
try:
    from update_checker import check_and_perform_update
    check_and_perform_update(local_version=VERSION)
except ImportError as e:
    print("[bootstrap] Warning: update_checker module not found. Skipping update check.")

# 5) Launch the bot
from ljb.twitch_bot import main
main()
