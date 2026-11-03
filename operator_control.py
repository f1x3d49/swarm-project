"""Fly config.OPERATOR_AGENT_ID by hand — W/A/S/D, 'q' to quit.

Run this in its own terminal, on this machine, alongside launch_sitl.py and
launch_swarm.py. It sends nothing but a commanded velocity over
swarm/operator_link.py's local UDP channel; the operator agent stays an
ordinary agent to every peer's world model (CLAUDE.md invariant #5) —
this script has no idea any other agent exists.

Controls: W = north, S = south, A = west, D = east, at config.MAX_SPEED_MPS.
No key held for OPERATOR_IDLE_TIMEOUT_S -> sends zero velocity (hover).
Diagonal combining isn't supported (last key wins) -- keep it simple.

Works in a Windows console (msvcrt) and a Linux terminal (termios). Must be
an interactive terminal — it reads raw keystrokes, so the window has to
have focus while you fly.

Usage: python operator_control.py
"""
import json
import os
import socket
import sys
import time

from swarm import config

OPERATOR_IDLE_TIMEOUT_S = 0.5  # no keypress within this window -> hover
SEND_HZ = 10

DIRECTIONS = {
    "w": (config.MAX_SPEED_MPS, 0.0, "north"),
    "s": (-config.MAX_SPEED_MPS, 0.0, "south"),
    "a": (0.0, -config.MAX_SPEED_MPS, "west"),
    "d": (0.0, config.MAX_SPEED_MPS, "east"),
}


if sys.platform == "win32":
    import msvcrt

    class KeyReader:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def read_key(self, timeout):
            """Newest key pressed within `timeout` seconds, lowercased, or None."""
            deadline = time.time() + timeout
            key = None
            while True:
                while msvcrt.kbhit():
                    ch = msvcrt.getwch()
                    if ch in ("\x00", "\xe0"):  # arrow/function key prefix: skip its second code
                        msvcrt.getwch()
                        continue
                    key = ch.lower()
                if key is not None or time.time() >= deadline:
                    return key
                time.sleep(0.01)
else:
    import select
    import termios
    import tty

    class KeyReader:
        def __enter__(self):
            self._fd = sys.stdin.fileno()
            self._old = termios.tcgetattr(self._fd)
            tty.setcbreak(self._fd)
            return self

        def __exit__(self, *exc):
            termios.tcsetattr(self._fd, termios.TCSADRAIN, self._old)
            return False

        def read_key(self, timeout):
            """Newest key pressed within `timeout` seconds, lowercased, or None.

            Drains everything pending: key auto-repeat outpaces SEND_HZ, and
            reading one char per tick would build a backlog that keeps the
            drone flying long after the key is released.
            """
            ready, _, _ = select.select([sys.stdin], [], [], timeout)
            if not ready:
                return None
            key = None
            while ready:
                data = os.read(self._fd, 1024)
                if not data:
                    break
                key = chr(data[-1]).lower()
                ready, _, _ = select.select([sys.stdin], [], [], 0)
            return key


def main():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    target = ("127.0.0.1", config.OPERATOR_INPUT_PORT)

    print(f"[operator] flying agent {config.OPERATOR_AGENT_ID}. "
          "W/A/S/D to move, 'q' to quit.")

    vn, ve, label = 0.0, 0.0, "hover"
    last_key_time = 0.0
    period = 1.0 / SEND_HZ

    try:
        with KeyReader() as keys:
            while True:
                tick_start = time.time()

                ch = keys.read_key(period)
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
        sock.close()
        print("\n[operator] stopped.")


if __name__ == "__main__":
    main()
