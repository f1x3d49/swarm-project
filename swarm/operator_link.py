"""One-way channel from operator_control.py (a human at a keyboard) to the
operator agent's process — see docs/ARCHITECTURE.md's operator-control step
and CLAUDE.md invariant #5. Never relayed to peers; this is not part of the
inter-agent comms layer (swarm/comms.py).
"""
import json
import socket
import time

from . import config


class OperatorLink:
    def __init__(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(("127.0.0.1", config.OPERATOR_INPUT_PORT))
        self.sock.setblocking(False)
        self._last_velocity = (0.0, 0.0, 0.0)
        self._last_rx_time = None

    def _drain(self):
        while True:
            try:
                data, _ = self.sock.recvfrom(4096)
            except BlockingIOError:
                break
            try:
                msg = json.loads(data.decode("utf-8"))
                self._last_velocity = (msg["vn"], msg["ve"], msg.get("vd", 0.0))
                self._last_rx_time = time.time()
            except (json.JSONDecodeError, KeyError):
                continue

    def get_commanded_velocity(self, now=None):
        """Latest (vn, ve, vd) from operator_control.py, or (0,0,0) if
        nothing has arrived yet or the last command is stale — fails safe
        (hover) rather than flying on a human input that stopped arriving.
        """
        self._drain()
        now = now if now is not None else time.time()
        if self._last_rx_time is None:
            return (0.0, 0.0, 0.0)
        if now - self._last_rx_time > config.OPERATOR_INPUT_STALE_TIMEOUT_S:
            return (0.0, 0.0, 0.0)
        return self._last_velocity

    def close(self):
        self.sock.close()
