"""Fly config.OPERATOR_AGENT_ID by hand — W/A/S/D, 'q' to quit.

Run this in its own terminal, on this machine, alongside launch_sitl.py and
launch_swarm.py. It sends nothing but a commanded velocity over
swarm/operator_link.py's local UDP channel; the operator agent stays an
ordinary agent to every peer's world model (CLAUDE.md invariant #5) —
this script has no idea any other agent exists.

Controls: W = north, S = south, A = west, D = east, at config.MAX_SPEED_MPS.
No key held for OPERATOR_IDLE_TIMEOUT_S -> sends zero velocity (hover).
Diagonal combining isn't supported (last key wins) -- keep it simple.

Usage: python3 operator_control.py
"""
import json
import os
import select
import socket
import sys
import termios
import time
import tty

from swarm import config

OPERATOR_IDLE_TIMEOUT_S = 0.5  # no keypress within this window -> hover
SEND_HZ = 10

DIRECTIONS = {
    "w": (config.MAX_SPEED_MPS, 0.0, "north"),
    "s": (-config.MAX_SPEED_MPS, 0.0, "south"),
    "a": (0.0, -config.MAX_SPEED_MPS, "west"),
    "d": (0.0, config.MAX_SPEED_MPS, "east"),
}


def read_newest_key(fd, timeout):
    """Newest key pressed within `timeout` seconds, lowercased, or None.

    Drains everything pending: key auto-repeat outpaces SEND_HZ, and reading
    one char per tick would build a backlog that keeps the drone flying long
    after the key is released.
    """
    ready, _, _ = select.select([fd], [], [], timeout)
    if not ready:
        return None
    key = None
    while ready:
        data = os.read(fd, 1024)
        if not data:
            break
        key = chr(data[-1]).lower()
        ready, _, _ = select.select([fd], [], [], 0)
    return key


def main():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    target = ("127.0.0.1", config.OPERATOR_INPUT_PORT)

    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    tty.setcbreak(fd)

    print(f"[operator] flying agent {config.OPERATOR_AGENT_ID}. "
          "W/A/S/D to move, 'q' to quit.")

    vn, ve, label = 0.0, 0.0, "hover"
    last_key_time = 0.0
    period = 1.0 / SEND_HZ

    try:
        while True:
            tick_start = time.time()

            ch = read_newest_key(fd, period)
            if ch is not None:
                if ch == "q":
                    break
                if ch in DIRECTIONS:
                    vn, ve, label = DIRECTIONS[ch]
                    last_key_time = time.time()
                    print(f"[operator] {label} ({vn:+.1f}, {ve:+.1f})", flush=True)

            if time.time() - last_key_time > OPERATOR_IDLE_TIMEOUT_S:
                if label != "hover":
                    print("[operator] hover", flush=True)
                vn, ve, label = 0.0, 0.0, "hover"

            sock.sendto(json.dumps({"vn": vn, "ve": ve, "vd": 0.0}).encode("utf-8"), target)

            time.sleep(max(0.0, period - (time.time() - tick_start)))
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
        sock.close()
        print("\n[operator] stopped.")


if __name__ == "__main__":
    main()
