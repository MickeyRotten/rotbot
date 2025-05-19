#!/usr/bin/env python3
import subprocess
import sys
import os
import time
import json
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8')

ASCII_ART_ROTSOFT = r"""


   ██▀███   ▒█████  ▄▄▄█████▓  ██████  ▒█████    █████▒▄▄▄█████▓
  ▓██ ▒ ██▒▒██▒  ██▒▓  ██▒ ▓▒▒██    ▒ ▒██▒  ██▒▓██   ▒ ▓  ██▒ ▓▒
  ▓██ ░▄█ ▒▒██░  ██▒▒ ▓██░ ▒░░ ▓██▄   ▒██░  ██▒▒████ ░ ▒ ▓██░ ▒░
  ▒██▀▀█▄  ▒██   ██░░ ▓██▓ ░   ▒   ██▒▒██   ██░░▓█▒  ░ ░ ▓██▓ ░ 
  ░██▓ ▒██▒░ ████▓▒░  ▒██▒ ░ ▒██████▒▒░ ████▓▒░░▒█░      ▒██▒ ░ 
  ░ ▒▓ ░▒▓░░ ▒░▒░▒░   ▒ ░░   ▒ ▒▓▒ ▒ ░░ ▒░▒░▒░  ▒ ░      ▒ ░░   
    ░▒ ░ ▒░  ░ ▒ ▒░     ░    ░ ░▒  ░ ░  ░ ▒ ▒░  ░          ░    
    ░░   ░ ░ ░ ░ ▒    ░      ░  ░  ░  ░ ░ ░ ▒   ░ ░      ░      
     ░         ░ ░                 ░      ░ ░                                                                               
"""

ASCII_ART_BOT = r"""
  ▄▄▌  ▪  ▄▄▌   ▐▄▄▄▄• ▄▌▪   ▄▄· ▄▄▄ .▄▄▄  
  ██•  ██ ██•    ·███▪██▌██ ▐█ ▌▪▀▄.▀·▀▄ █·
  ██▪  ▐█·██▪  ▪▄ ███▌▐█▌▐█·██ ▄▄▐▀▀▪▄▐▀▀▄ 
  ▐█▌▐▌▐█▌▐█▌▐▌▐▌▐█▌▐█▄█▌▐█▌▐███▌▐█▄▄▌▐█•█▌
  .▀▀▀ ▀▀▀.▀▀▀  ▀▀▀• ▀▀▀ ▀▀▀·▀▀▀  ▀▀▀ .▀  ▀         
"""

def fake_loading_bar(text="loading", total=30, delay=0.04):
    for i in range(total + 1):
        percent = int(100 * i / total)
        bar = "█" * i + '-' * (total - i)
        print(f"\r{text}: |{bar}| {percent}%", end="", flush=True)
        time.sleep(delay)
    print(" Done!\n")

def print_divider():
    print("\n" + "#" * 73 + "\n")

def ensure_requirements_installed():
    """Install all core requirements from requirements.txt, only if needed."""
    try:
        import pkg_resources
        with open("requirements.txt") as req:
            packages = [line.strip() for line in req if line.strip() and not line.startswith("#")]
        try:
            pkg_resources.require(packages)
            return
        except (pkg_resources.DistributionNotFound, pkg_resources.VersionConflict):
            print("[bootstrap] installing missing core dependencies from requirements.txt...")
            subprocess.check_call([sys.executable, "-m", "pip", "install", "--user", "-r", "requirements.txt"])
    except ImportError:
        print("[bootstrap] installing core dependencies from requirements.txt...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "--user", "-r", "requirements.txt"])

def install_addon_requirements(addons_dir="addons"):
    """Scan each addon's requirements.txt and install only if required, with confirmation output."""
    try:
        import pkg_resources
    except ImportError:
        print("[bootstrap] installing all addon requirements...")
        for addon in Path(addons_dir).iterdir():
            req = addon / "requirements.txt"
            if req.exists():
                subprocess.check_call([sys.executable, "-m", "pip", "install", "--user", "-r", str(req)])
        return

    addons_path = Path(addons_dir)
    if not addons_path.exists():
        return
    for addon in addons_path.iterdir():
        req = addon / "requirements.txt"
        if req.exists():
            with req.open() as reqf:
                packages = [line.strip() for line in reqf if line.strip() and not line.startswith("#")]
            try:
                pkg_resources.require(packages)
                print(f"[bootstrap] all requirements satisfied for addon '{addon.name}'.")
            except (pkg_resources.DistributionNotFound, pkg_resources.VersionConflict):
                print(f"[bootstrap] installing requirements for addon '{addon.name}'...")
                subprocess.check_call([sys.executable, "-m", "pip", "install", "--user", "-r", str(req)])

def list_loaded_addons(addons_dir="addons"):
    """Print a list of all detected/loaded addons (those with addon.py), and return dict of versions."""
    addons_path = Path(addons_dir)
    versions = {}
    if not addons_path.exists():
        print("no addons directory found.")
        return versions
    loaded = []
    for addon in sorted(addons_path.iterdir()):
        if addon.is_dir() and (addon / "addon.py").exists():
            loaded.append(addon.name)
            # Read version.txt if exists
            vfile = addon / "version.txt"
            if vfile.exists():
                versions[addon.name] = vfile.read_text().strip()
            else:
                versions[addon.name] = "unknown"
    if loaded:
        print("loaded addons: " + ", ".join(f"{n} (v{versions[n]})" for n in loaded))
    else:
        print("no addons found.")
    return versions

def read_core_version():
    version_file = Path(__file__).parent / "version.txt"
    if version_file.exists():
        return version_file.read_text().strip()
    return "unknown"

def main_menu():
    while True:
        print_divider()
        print(ASCII_ART_BOT)
        print("select an option:")
        print("")
        print("  1) launch bot")
        print("  2) configure bot")
        print("  3) manage addons")
        print("  4) reset all user tokens")
        print("  5) exit")
        choice = input("\nenter your choice: ").strip()
        if choice == "1":
            launch_bot()
        elif choice == "2":
            configure_bot()
        elif choice == "3":
            manage_addons()
        elif choice == "4":
            reset_user_tokens()
        elif choice == "5":
            print("bye! thanks for using lilrotbot.")
            time.sleep(1)
            break
        else:
            print("invalid choice. please select a number from the menu.")

def launch_bot():
    print_divider()
    print("launching lilrotbot. the bot console will now run below.\n")
    time.sleep(0.7)
    from ljb.twitch_bot import main
    main()  # Hands over control to the bot

def configure_bot():
    print_divider()
    print("configuration is not yet implemented.")
    print("for now, edit 'config.json' or '.env' directly.")
    time.sleep(1.5)

def manage_addons():
    print_divider()
    print("addon management is not yet implemented.")
    print("addons can be managed by placing/removing folders in the 'addons/' directory.")
    time.sleep(1.5)
    
def reset_user_tokens():
    print_divider()
    # 1. Reset core config.json tokens
    config_path = Path("config.json")
    if config_path.exists():
        with config_path.open("r", encoding="utf-8") as f:
            cfg = json.load(f)
        preserved = {}
        # List fields you want to preserve:
        PRESERVE_FIELDS = ["bot_nick"]
        for k in PRESERVE_FIELDS:
            if k in cfg:
                preserved[k] = cfg[k]
        # Now wipe sensitive entries (tokens)
        token_fields = [
            "streamer_access_token", "streamer_refresh_token",
            "twitch_channel"
        ]
        for field in token_fields:
            cfg[field] = None
        # Restore preserved fields
        for k, v in preserved.items():
            cfg[k] = v
        with config_path.open("w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
        print("[reset] core config.json tokens reset.")
    else:
        print("[reset] config.json not found.")

    # 2. Delete addon_tokens.json for each addon
    addons_dir = Path("addons")
    n = 0
    if addons_dir.exists():
        for addon in addons_dir.iterdir():
            addon_token_file = addon / "addon_tokens.json"
            if addon_token_file.exists():
                addon_token_file.unlink()
                print(f"[reset] Deleted {addon_token_file}")
                n += 1
    print(f"[reset] {n} addon token file(s) removed.")

    print_divider()
    print("all user tokens and OAuth credentials have been reset.")
    print("you will need to re-authorize on next launch.")
    input("press enter to return to the menu...")

def check_for_updates_auto(core_version, addon_versions):
    try:
        from update_checker import check_and_perform_update
        check_and_perform_update(core_version=core_version, addon_versions=addon_versions)
    except ImportError:
        print("[bootstrap] warning: update_checker module not found. skipping update check.")
    time.sleep(0.2)

if __name__ == "__main__":
    os.system('cls' if os.name == 'nt' else 'clear')
    print(ASCII_ART_ROTSOFT)

    # Show fake loading bar and versions
    print_divider()
    fake_loading_bar("loading core", total=40, delay=0.04)
    CORE_VERSION = read_core_version()
    print(f"loaded core version: {CORE_VERSION}")
    print_divider()
    fake_loading_bar("loading addons", total=38, delay=0.03)
    addon_versions = list_loaded_addons()
    print_divider()
    
    # Install requirements from requirements.txt
    ensure_requirements_installed()

    # Install requirements for all addons (if any)
    install_addon_requirements()

    # Automatic update check before menu
    check_for_updates_auto(CORE_VERSION, addon_versions)

    main_menu()
