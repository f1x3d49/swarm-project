"""Start one ArduCopter SITL instance per agent — native Windows, no MAVProxy.

Companion to launch_swarm.py: this provides the "simulators already
running" prerequisite that swarm/agent.py assumes, using the ports and ids in
swarm/config.py as the single source of truth (CLAUDE.md #6).

Each instance is the simulator binary started directly (no sim_vehicle.py),
with two MAVLink outputs (see config.py's simulator section):
  SERIAL0  TCP config.SITL_PORTS[n]       -> that agent's own connection
  SERIAL1  UDP push to Mission Planner    -> config.MISSION_PLANNER_PORTS[n]

Windows: runs sitl_bin/ArduCopter.elf — run `python fetch_sitl.py` once first.
Linux (only for testing this branch from WSL): runs the locally built
config.SITL_LINUX_BINARY instead.

Every launch wipes the simulated EEPROM, so no state carries over between
runs (CLAUDE.md: always restart SITL between experiments).

Usage: python launch_sitl.py
Ctrl+C stops every instance. Per-instance output goes to sitl_logs/<n>/sitl.log.
"""
import os
import subprocess
import sys
import time

from swarm import config

REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
LOG_DIR = os.path.join(REPO_ROOT, "sitl_logs")
BIN_DIR = os.path.join(REPO_ROOT, config.SITL_BIN_DIR)


def simulator_binary():
    if sys.platform == "win32":
        exe = os.path.join(BIN_DIR, config.SITL_WINDOWS_EXE)
        if not os.path.exists(exe):
            sys.exit(f"[launch_sitl] {exe} not found — run `python fetch_sitl.py` first.")
        return exe
    exe = os.path.expanduser(config.SITL_LINUX_BINARY)
    if not os.path.exists(exe):
        sys.exit(f"[launch_sitl] {exe} not found — build ArduPilot SITL "
                 "(./waf configure --board sitl && ./waf copter).")
    return exe


def defaults_files():
    """copter.parm (downloaded by fetch_sitl.py) followed by the repo's own
    config.SITL_EXTRA_DEFAULTS — later files override earlier ones."""
    parm = os.path.join(BIN_DIR, config.SITL_DEFAULTS_FILE)
    if not os.path.exists(parm):
        sys.exit(f"[launch_sitl] {parm} not found — run `python fetch_sitl.py` first.")
    return [parm] + [os.path.join(REPO_ROOT, p) for p in config.SITL_EXTRA_DEFAULTS]


def main():
    exe = simulator_binary()
    parms = defaults_files()

    procs = {}
    for agent_id in config.AGENT_IDS:
        instance_dir = os.path.join(LOG_DIR, str(agent_id))
        os.makedirs(instance_dir, exist_ok=True)

        cmd = [
            exe,
            "--wipe",
            f"-I{agent_id}",
            "--model", "+",
            "--home", config.SITL_HOME,
            "--sysid", str(config.SITL_SYSIDS[agent_id]),
            # Relative, forward-slash path: works for both the Cygwin build on
            # Windows and the native Linux build, without path translation.
            "--defaults", ",".join(os.path.relpath(p, instance_dir).replace("\\", "/")
                                   for p in parms),
            "--serial1", f"udpclient:{config.MISSION_PLANNER_HOST}:"
                         f"{config.MISSION_PLANNER_PORTS[agent_id]}",
        ]
        log_path = os.path.join(instance_dir, "sitl.log")
        log_file = open(log_path, "w")
        p = subprocess.Popen(cmd, cwd=instance_dir, stdout=log_file, stderr=subprocess.STDOUT)
        procs[agent_id] = (p, log_file)
        print(f"[launch_sitl] instance {agent_id}: pid={p.pid}, agent tcp:{config.SITL_PORTS[agent_id]}, "
              f"Mission Planner udp:{config.MISSION_PLANNER_PORTS[agent_id]}, log={log_path}", flush=True)

    print("[launch_sitl] all instances started. Each one waits for its agent to connect "
          "before simulating — start launch_swarm.py next.", flush=True)
    print("[launch_sitl] Ctrl+C to stop all instances.", flush=True)

    try:
        while True:
            for agent_id, (p, _f) in procs.items():
                if p.poll() is not None:
                    raise RuntimeError(f"instance {agent_id} exited (code {p.returncode}) — "
                                       f"see sitl_logs/{agent_id}/sitl.log")
            time.sleep(1)
    except KeyboardInterrupt:
        print("[launch_sitl] stopping all instances...", flush=True)
    except RuntimeError as e:
        print(f"[launch_sitl] {e}; stopping the rest.", flush=True)
    finally:
        for p, _f in procs.values():
            if p.poll() is None:
                p.terminate()
        for agent_id, (p, f) in procs.items():
            try:
                p.wait(timeout=5)
            except subprocess.TimeoutExpired:
                p.kill()
                p.wait(timeout=5)
            f.close()

    print("[launch_sitl] done.", flush=True)


if __name__ == "__main__":
    main()
