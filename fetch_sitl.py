"""Download the ArduCopter simulator for Windows into config.SITL_BIN_DIR.

One-time setup step before launch_sitl.py. Fetches ArduPilot's official
prebuilt Windows SITL (a Cygwin build — the same binaries Mission Planner's
own Simulation screen downloads) plus the Cygwin DLLs it needs, and the
standard copter defaults file (copter.parm) from the exact ArduPilot commit
that binary was built from, so the two always match.

Usage: python fetch_sitl.py           (skips files already downloaded)
       python fetch_sitl.py --force   (re-download everything)
"""
import argparse
import os
import re
import sys
import urllib.parse
import urllib.request

from swarm import config

BASE_URL = "https://firmware.ardupilot.org/Tools/MissionPlanner/sitl/CopterStable/"
FILES = [
    config.SITL_WINDOWS_EXE,
    "cygatomic-1.dll",
    "cyggcc_s-1.dll",
    "cyggcc_s-seh-1.dll",
    "cyggomp-1.dll",
    "cygiconv-2.dll",
    "cygintl-8.dll",
    "cygquadmath-0.dll",
    "cygssp-0.dll",
    "cygstdc++-6.dll",
    "cygwin1.dll",
]
PARM_URL = ("https://raw.githubusercontent.com/ArduPilot/ardupilot/{commit}/"
            "Tools/autotest/default_params/copter.parm")


def download(url, path):
    print(f"[fetch_sitl] {url}", flush=True)
    with urllib.request.urlopen(url, timeout=120) as resp, open(path + ".part", "wb") as out:
        while True:
            chunk = resp.read(1 << 16)
            if not chunk:
                break
            out.write(chunk)
    os.replace(path + ".part", path)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true", help="re-download files that already exist")
    args = parser.parse_args()

    repo_root = os.path.dirname(os.path.abspath(__file__))
    bin_dir = os.path.join(repo_root, config.SITL_BIN_DIR)
    os.makedirs(bin_dir, exist_ok=True)

    for name in FILES:
        path = os.path.join(bin_dir, name)
        if os.path.exists(path) and not args.force:
            print(f"[fetch_sitl] have {name}", flush=True)
            continue
        download(BASE_URL + urllib.parse.quote(name), path)

    # git.txt records which ArduPilot commit the binary was built from.
    with urllib.request.urlopen(BASE_URL + "git.txt", timeout=60) as resp:
        git_txt = resp.read().decode("utf-8", "replace")
    match = re.search(r"commit ([0-9a-f]{40})", git_txt)
    if not match:
        sys.exit("[fetch_sitl] could not read the build commit from git.txt")
    commit = match.group(1)
    with open(os.path.join(bin_dir, "git.txt"), "w", encoding="utf-8") as f:
        f.write(git_txt)

    parm_path = os.path.join(bin_dir, config.SITL_DEFAULTS_FILE)
    if os.path.exists(parm_path) and not args.force:
        print(f"[fetch_sitl] have {config.SITL_DEFAULTS_FILE}", flush=True)
    else:
        download(PARM_URL.format(commit=commit), parm_path)

    print(f"[fetch_sitl] done. Simulator built from ArduPilot commit {commit[:10]}, "
          f"files in {bin_dir}", flush=True)


if __name__ == "__main__":
    main()
