"""
addon_loader.py
Scans /addons/, imports every ljb_* add-on safely,
returns (mods, dirs, extra_scopes)
Each add-on can optionally define:
  • scopes : list[str|AuthScope]
  • register(bot, folder)
  • start(bot) -> coroutine
"""

from __future__ import annotations
import importlib.util, json, os, sys
from pathlib import Path
from twitchAPI.type import AuthScope

def discover(addons_dir: Path):
    mods      = []
    dirs      = []
    extra     = []

    for folder in addons_dir.iterdir():
        if not folder.name.startswith("ljb_"):
            continue
        addon_py = folder / "addon.py"
        if not addon_py.exists():
            continue
        try:
            spec = importlib.util.spec_from_file_location(folder.name, addon_py)
            mod  = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            mods.append(mod); dirs.append(folder)

            extra.extend(
                AuthScope(s) if isinstance(s, str) else s
                for s in getattr(mod, "scopes", [])
            )
        except Exception as e:
            print(f"[Addon load error] {folder.name}: {e}", file=sys.stderr)

    return mods, dirs, extra
