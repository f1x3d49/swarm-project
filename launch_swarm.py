"""Spawn one independent OS process per agent (CLAUDE.md invariant #1).

This script issues no MAVLink commands itself and reads no vehicle state —
it only starts and stops subprocesses. If you find yourself adding logic
here that reads a vehicle's state or computes a command, that logic belongs
in swarm/agent.py instead.

Prerequisite: launch_sitl.py running (CLAUDE.md: always restart SITL
between experiments). Agents retry their connection for
config.CONNECT_TIMEOUT_S, so it's fine to start this right after it.

Usage: python launch_swarm.py
Ctrl+C stops all agents. To test node death, kill one agent's PID directly
(printed at startup) — `taskkill /F /PID <pid>` on Windows, `kill -9 <pid>`
on Linux — and watch the survivors' world-model logs.
"""
import subprocess
import sys
import time

from swarm import config

procs = {}
for agent_id in config.AGENT_IDS:
    p = subprocess.Popen([sys.executable, "-m", "swarm.agent", "--id", str(agent_id)])
    procs[agent_id] = p
    print(f"[launch] agent {agent_id} pid={p.pid}")

kill_cmd = "taskkill /F /PID <pid>" if sys.platform == "win32" else "kill -9 <pid>"
print(f"[launch] all agents started. Ctrl+C to stop all, "
      f"or `{kill_cmd}` one to test node death.")

try:
    while any(p.poll() is None for p in procs.values()):
        time.sleep(1)
except KeyboardInterrupt:
    print("[launch] stopping all agents...")
    for agent_id, p in procs.items():
        if p.poll() is None:
            p.terminate()
    for p in procs.values():
        p.wait()

print("[launch] done.")
