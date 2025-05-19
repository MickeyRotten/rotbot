# update_versions_json.py

import json
from pathlib import Path

def main():
    root = Path(__file__).parent
    # Read core version
    core_version_file = root / "version.txt"
    core_version = core_version_file.read_text().strip() if core_version_file.exists() else "unknown"
    # Read addon versions
    addons_dir = root / "addons"
    addons = {}
    if addons_dir.exists():
        for addon in addons_dir.iterdir():
            if addon.is_dir():
                vfile = addon / "version.txt"
                if vfile.exists():
                    # Optionally add download_url if needed:
                    # addons[addon.name] = {
                    #     "version": vfile.read_text().strip(),
                    #     "download_url": f"https://github.com/MickeyRotten/rotbot/releases/latest/download/{addon.name}.zip"
                    # }
                    addons[addon.name] = vfile.read_text().strip()
    versions = {
        "core": core_version,
        "addons": addons
    }
    with open(root / "versions.json", "w", encoding="utf-8") as f:
        json.dump(versions, f, indent=2)
    print("versions.json updated!")

if __name__ == "__main__":
    main()
