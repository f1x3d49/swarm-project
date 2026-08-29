"""Spawn 3 SITL instances, each with a MAVProxy relay in front of it.

Companion to launch_swarm.py — this handles the "3 SITL instances already
running" prerequisite that launch_swarm.py and swarm/agent.py assume, using
the exact ports/gains from swarm/config.py as the single source of truth
(CLAUDE.md #6) rather than hand-typed shell commands.

Each instance's MAVProxy fans its MAVLink stream out to two places (see
CLAUDE.md "known environment traps" and docs/ARCHITECTURE.md): a local UDP
port this agent's own process connects to (config.AGENT_LOCAL_MAVLINK_PORTS),
and a UDP push to Mission Planner on config.MISSION_PLANNER_HOST — an
outbound push, not a listener, so it needs no inbound firewall rule on this
(org-managed, no-admin) machine.

Usage: python3 launch_sitl.py
Ctrl+C tears down every instance and its MAVProxy/xterm children (uses
process groups — a bare kill on just the sim_vehicle.py PID leaves orphans,
learned the hard way during week 3 testing).

CLAUDE.md: always restart SITL between experiments — Ctrl+C this and rerun
rather than reusing a running instance.
"""
import os
import signal
import subprocess
import sys
import time

from swarm import config

SIM_VEHICLE = os.path.expanduser("~/ardupilot/Tools/autotest/sim_vehicle.py")
LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sitl_logs")

procs = {}
for agent_id in config.AGENT_IDS:
    instance_dir = os.path.join(LOG_DIR, str(agent_id))
    os.makedirs(instance_dir, exist_ok=True)

    cmd = [
        sys.executable, SIM_VEHICLE,
        "-v", "ArduCopter", f"-I{agent_id}", "--no-rebuild",
        "-m", "--daemon",
        f"--out=udp:127.0.0.1:{config.AGENT_LOCAL_MAVLINK_PORTS[agent_id]}",
        f"--out=udp:{config.MISSION_PLANNER_HOST}:{config.MISSION_PLANNER_PORTS[agent_id]}",
    ]
    print(f"[launch_sitl] instance {agent_id}: {' '.join(cmd)}", flush=True)

    log_path = os.path.join(instance_dir, "sitl.log")
    log_file = open(log_path, "w")
    p = subprocess.Popen(cmd, cwd=instance_dir, stdout=log_file, stderr=subprocess.STDOUT,
                          preexec_fn=os.setsid)  # own process group, so we can kill all descendants
    procs[agent_id] = p
    print(f"[launch_sitl] instance {agent_id} pid={p.pid}, log={log_path}", flush=True)

print("[launch_sitl] all instances launching. GPS/EKF position estimate "
      "typically takes 60-90s to settle before arming will succeed "
      "(CLAUDE.md known trap) — wait before running launch_swarm.py.", flush=True)
print("[launch_sitl] Ctrl+C to stop all instances.", flush=True)


def _killpg(pid, sig):
    """A process's group can already be gone by the time we get here (it
    exited on its own, or a sibling's kill already reaped it) — that's not
    an error, so don't let it abort the rest of the cleanup loop.
    """
    try:
        os.killpg(os.getpgid(pid), sig)
    except (ProcessLookupError, PermissionError):
        pass


try:
    while any(p.poll() is None for p in procs.values()):
        time.sleep(1)
except KeyboardInterrupt:
    print("[launch_sitl] stopping all instances (and their MAVProxy/xterm children)...", flush=True)
    for agent_id, p in procs.items():
        if p.poll() is None:
            _killpg(p.pid, signal.SIGTERM)
    deadline = time.time() + 5
    for agent_id, p in procs.items():
        remaining = max(0.0, deadline - time.time())
        try:
            p.wait(timeout=remaining)
        except subprocess.TimeoutExpired:
            _killpg(p.pid, signal.SIGKILL)
            try:
                p.wait(timeout=5)
            except subprocess.TimeoutExpired:
                print(f"[launch_sitl] instance {agent_id} (pid={p.pid}) did not "
                      "die even after SIGKILL — check manually", flush=True)

print("[launch_sitl] done.", flush=True)
