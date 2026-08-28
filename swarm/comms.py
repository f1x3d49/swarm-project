"""COMMS layer — "what do peers tell me?" See docs/ARCHITECTURE.md Section 3.

Stage 0 (current): perfect delivery. Implemented as unicast fan-out to every
other agent's known port rather than a real UDP broadcast/multicast address,
because that's simpler to get right on WSL2/localhost — but the interface
(`broadcast(msg)` / `receive() -> [(msg, rx_time)]`) is the real one. Stage 1
(packet loss, latency, range limit) drops in as per-destination logic inside
`broadcast()` without changing this interface or its callers.
"""
import json
import socket
import time

from . import config


class Comms:
    def __init__(self, agent_id):
        self.agent_id = agent_id
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(("127.0.0.1", config.COMMS_PORTS[agent_id]))
        self.sock.setblocking(False)

    def broadcast(self, msg: dict):
        payload = dict(msg)
        payload["sender_id"] = self.agent_id
        payload["send_time"] = time.time()
        data = json.dumps(payload).encode("utf-8")
        for peer_id, port in config.COMMS_PORTS.items():
            if peer_id == self.agent_id:
                continue
            self.sock.sendto(data, ("127.0.0.1", port))

    def receive(self):
        """Drain the socket. Returns [(msg_dict, rx_time), ...]."""
        out = []
        while True:
            try:
                data, _ = self.sock.recvfrom(4096)
            except BlockingIOError:
                break
            try:
                msg = json.loads(data.decode("utf-8"))
            except json.JSONDecodeError:
                continue
            out.append((msg, time.time()))
        return out

    def close(self):
        self.sock.close()
