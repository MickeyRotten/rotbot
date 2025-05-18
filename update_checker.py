# update_checker.py

import requests
import zipfile
import shutil
import os
import sys
import tempfile
from pathlib import Path
import glob

GITHUB_VERSION_URL = "https://raw.githubusercontent.com/MickeyRotten/rotbot/main/version.txt"
GITHUB_ZIP_URL = "https://github.com/MickeyRotten/rotbot/archive/refs/heads/main.zip"

PRESERVE_FILES = [
    ".env",
    "config.json"
]
PRESERVE_PATTERNS = [
    "addons/*/addon_tokens.json",
    "logs/*"
]

def check_and_perform_update(local_version: str):
    try:
        r = requests.get(GITHUB_VERSION_URL)
        r.raise_for_status()
        latest = r.text.strip()
    except Exception as e:
        print("Error checking for update:", e)
        return

    if latest != local_version:
        print(f"Update available! Latest: {latest}, You: {local_version}")
        do_update = input("Download and install update? (Y/N): ").strip().lower()
        if do_update == "y":
            update_rotbot()
            sys.exit(0)
        else:
            print("Continuing with current version.")
    else:
        print("You are up to date.")

def update_rotbot():
    print("Downloading and installing latest version...")
    with tempfile.TemporaryDirectory() as tmpdir:
        zip_path = os.path.join(tmpdir, "main.zip")
        with requests.get(GITHUB_ZIP_URL, stream=True) as r:
            with open(zip_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
        with zipfile.ZipFile(zip_path, "r") as zip_ref:
            zip_ref.extractall(tmpdir)
        extracted_dir = next(Path(tmpdir).glob("rotbot-*"))
        preserved = {}
        for filename in PRESERVE_FILES:
            file_path = Path(filename)
            if file_path.exists():
                preserved[filename] = file_path.read_bytes()
        for pattern in PRESERVE_PATTERNS:
            for found in glob.glob(pattern, recursive=True):
                path = Path(found)
                preserved[found] = path.read_bytes()
        for root, dirs, files in os.walk(extracted_dir):
            rel_dir = os.path.relpath(root, extracted_dir)
            if rel_dir == ".":
                rel_dir = ""
            for file in files:
                src_file = os.path.join(root, file)
                dst_file = os.path.join(os.getcwd(), rel_dir, file)
                preserve = False
                rel_path = os.path.normpath(os.path.join(rel_dir, file))
                if rel_path in preserved:
                    preserve = True
                for pattern in PRESERVE_PATTERNS:
                    for found in glob.glob(pattern, recursive=True):
                        if rel_path == os.path.normpath(found):
                            preserve = True
                if preserve:
                    continue
                os.makedirs(os.path.dirname(dst_file), exist_ok=True)
                shutil.copy2(src_file, dst_file)
        for filename, content in preserved.items():
            path = Path(filename)
            os.makedirs(path.parent, exist_ok=True)
            path.write_bytes(content)
    print("Update installed!")
    try:
        if sys.platform == "win32":
            print("Relaunching launch_bot.bat ...")
            os.system('start launch_bot.bat')
        else:
            print("Please re-launch the bot manually.")
    except Exception as e:
        print("Failed to relaunch automatically. Please start launch_bot.bat manually.")
