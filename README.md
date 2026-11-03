# Swarm Project — decentralized drone flocking in ArduPilot SITL

Three simulated ArduCopter drones fly as a flock using local rules only
(Reynolds separation / alignment / cohesion). A human pilots one of them with
the keyboard; the other two are never told who the pilot is — they see it as
an ordinary neighbor and follow it because flocking pulls them along.

Scope: flight coordination research only. No weapons, payloads, or targeting.

This is the **development branch (`main`)**: it runs under **WSL2 / Ubuntu
22.04** with a source build of ArduPilot, and shows the swarm on Mission
Planner running on another PC. To run it natively on Windows with Mission
Planner on the same PC, use the **`handoff`** branch instead.

- Design rules and project status: [`CLAUDE.md`](CLAUDE.md)
- Layer structure, interfaces, and roadmap: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)

---

## What you will see

1. Three drones take off from the same spot and push apart (the safety veto
   fires for the first few seconds — that is expected, see below).
2. Agents 0 and 2 fly toward a scripted waypoint 40 m north / 40 m east,
   flocking as they go. Agent 1 is the operator's drone.
3. When you fly agent 1 with W/A/S/D, the others bend toward it through
   cohesion and alignment — there is no leader-following code anywhere.
4. After 120 s every agent lands on its own and writes a metrics CSV.

Each agent is a separate OS process with its own MAVLink connection and its
own world model. No process ever reads another drone's state directly;
everything an agent knows about its peers arrived over the (simulated) comms
link and decays if it stops arriving.

---

## Requirements

- Ubuntu 22.04 under WSL2 (native Ubuntu works too). Python 3.10.
- **ArduPilot checked out at `~/ardupilot`** with the copter SITL already
  built. `launch_sitl.py` hardcodes that path and passes `--no-rebuild`, so
  the build must exist before you start. Following ArduPilot's own setup
  guide ("Setting up the Build Environment (Linux/Ubuntu)" on
  ardupilot.org), that is roughly:

  ```bash
  cd ~
  git clone --recurse-submodules https://github.com/ArduPilot/ardupilot.git
  cd ardupilot
  Tools/environment_install/install-prereqs-ubuntu.sh -y
  . ~/.profile
  ./waf configure --board sitl
  ./waf copter
  ```

  Sanity check: `~/ardupilot/build/sitl/bin/arducopter` exists.
- Python packages: `pymavlink`, `MAVProxy`, `numpy`. The ArduPilot prereqs
  script installs the first two; to be sure:

  ```bash
  pip install --user pymavlink MAVProxy numpy
  ```

- **Optional, for the map view:** Mission Planner on a Windows PC on the same
  network. Without it everything still runs — you just watch terminal logs
  and CSVs instead of a map.

---

## One-time configuration

All ports, gains, and addresses live in [`swarm/config.py`](swarm/config.py).
The only value you are likely to need to change:

```python
MISSION_PLANNER_HOST = "192.168.1.135"   # LAN IP of the PC running Mission Planner
```

Set it to the LAN IP of the PC running Mission Planner. If you have no
Mission Planner, leave it — UDP sent to an absent host is harmless.

Each drone's MAVProxy relay pushes telemetry to Mission Planner on **UDP
ports 14550, 14551, 14552** (one per drone; `MISSION_PLANNER_PORTS`). Set
Mission Planner to listen on all three so every vehicle appears on the map.
Windows Firewall on the Mission Planner PC may ask to allow it — allow it.

---

## Running it

Three terminals, **all from the repo root**.

**Terminal 1 — simulators**

```bash
python3 launch_sitl.py
```

Starts 3 ArduCopter SITL instances through `sim_vehicle.py`, each with a
MAVProxy relay that forwards telemetry to its agent and to Mission Planner.
Per-instance logs go to `sitl_logs/<id>/sitl.log`. Wait about 60–90 s for
GPS/EKF to settle before the next step (agents also wait up to 120 s for
prearm checks on their own).

**Terminal 2 — the swarm**

```bash
python3 launch_swarm.py
```

Starts one `swarm.agent` process per drone and prints their PIDs. Each agent
waits for prearm checks, arms, takes off to 10 m, then runs the flocking loop
at 5 Hz for 120 s and lands. Every second each agent prints its world model:

```
[agent 0] world model: {1: pos=(12.3, 8.1) age=0.2s conf=0.96, 2: ...}
```

**Terminal 3 — the operator** (start once the drones are airborne)

```bash
python3 operator_control.py
```

| Key | Action |
|---|---|
| W / S | fly agent 1 north / south at 3 m/s |
| A / D | fly agent 1 west / east |
| no key for 0.5 s | hover |
| q | quit (agent 1 hovers; it stays in the flock) |

Hold a key down — the terminal's key-repeat keeps the command alive. This
must run in a real interactive terminal (it reads raw keystrokes).

**Optional — node death.** Kill one agent with `kill -9 <pid>` using a PID
from terminal 2. The survivors drop it from their world models after 5 s of
silence (`dropping stale entity ...`) and λ₂ in their CSVs falls. The dead
drone's simulator keeps it hovering in place. This has been tried but a full
"swarm heals" run has not been verified.

**Shutting down / running again**

- Ctrl+C in terminal 2 stops the agents (they also exit on their own after
  120 s).
- Ctrl+C in terminal 1 stops every simulator and its MAVProxy. Do not kill
  `sim_vehicle.py` by PID — that leaves orphan processes.
- **Restart the simulators before every run.** Leftover state from a previous
  run contaminates the next one.

---

## Reading the results

Each agent writes `results/metrics_agent<id>_<HHMMSS>.csv`, computed only
from that agent's own world model:

| Column | Meaning |
|---|---|
| `t` | seconds since the agent's flocking loop started |
| `phi` | order parameter (Vicsek 1995): 1.0 = all headings aligned, 0 = none |
| `min_neighbor_dist_m` | distance to the nearest peer this agent can see |
| `lambda2` | algebraic connectivity of the neighbor graph; 3.0 = fully connected 3-agent swarm, 0 = fragmented |
| `veto` | `MIN_SEPARATION` or `GEOFENCE` if the safety layer overrode the behaviors that tick |

New runs land directly in `results/` (gitignored). The subfolders are
recorded runs, grouped by the development step they were committed with:

| Folder | Run |
|---|---|
| `week2_flocking` | Reynolds flocking toward the waypoint (no λ₂ column yet) |
| `week3_lambda2` | Adds the gossiped neighbor graph and λ₂ |
| `week3_mp_relay` | Same swarm, with telemetry relayed to a remote Mission Planner |
| `week4_operator_first` | An earlier operator-control run |
| `week4_operator_reference` | **Reference run** with the operator flying agent 1: φ ends at about 0.99 for all three agents and λ₂ stays at 3.0 |

Quick plot (needs `matplotlib`):

```bash
python3 -c "
import csv, sys, matplotlib.pyplot as plt
for f in sys.argv[1:]:
    r = list(csv.DictReader(open(f)))
    plt.plot([float(x['t']) for x in r], [float(x['phi']) for x in r], label=f)
plt.xlabel('t (s)'); plt.ylabel('phi'); plt.legend(); plt.show()
" results/week4_operator_reference/*.csv
```

---

## Things that look like bugs but are expected

- **`SAFETY VETO: MIN_SEPARATION` spam at startup, and `min_neighbor_dist_m`
  of 0.0.** All three SITL instances spawn at the same home location. The
  veto pushes them apart in the first few seconds.
- **φ = 0 in the first rows.** Hovering agents have no heading, so they are
  excluded from φ until they move.
- **Agent 1 just hovers** if `operator_control.py` isn't running. It still
  flocks with its neighbors; it just has no objective of its own.

---

## Honest limitations

- **Peers are announced, not sensed.** Each agent broadcasts its own
  simulated GPS position. Nothing perceives terrain, structures, people, or
  other aircraft.
- **Comms are perfect.** Packet loss, latency, and range limits are designed
  (`docs/ARCHITECTURE.md` §3) but not built.
- **Positions are SITL ground truth.** No GPS noise model yet.
- **The 2 m separation floor is reactive, not a guarantee.** In the
  reference run, after the initial spread, the closest approach was 0.8 m —
  the veto fired and pushed the drones apart, but only after the floor was
  crossed. SITL instances don't physically collide, so this shows up only in
  the CSV.
- **A killed agent becomes invisible, not avoided.** Survivors forget it
  after 5 s, but its simulated drone is still hovering at flock altitude.
- **Safety veto covers geofence (60 m) and separation only.** Battery,
  comms-loss, and altitude limits are not built.

---

## Repo map

| Path | What |
|---|---|
| `launch_sitl.py`, `launch_swarm.py`, `operator_control.py` | The three entry points above |
| `swarm/config.py` | Every port, gain, radius, timeout, and output folder |
| `swarm/agent.py` | One agent: connect, take off, 5 Hz sense → decide → act loop |
| `swarm/state.py` | `StateEstimate` / `TrackedEntity` — positions always carry uncertainty, time, source, validity |
| `swarm/comms.py` | Inter-agent messaging (stage 0: perfect delivery over local UDP) |
| `swarm/behaviors.py` | Separation, alignment, cohesion, group objective, operator input |
| `swarm/arbiter.py` | Weighted blend, speed limit, safety veto |
| `swarm/metrics.py`, `swarm/graph.py` | φ, min distance, λ₂, CSV logging |
| `swarm/operator_link.py` | Keyboard → operator agent channel (never seen by peers) |
| `results/` | Metrics from new runs, plus recorded runs in subfolders |
| `docs/ARCHITECTURE.md` | Layer design, interfaces, and the roadmap |
| `archive/leader_follower/` | The earlier leader–follower phase (scripts, notes, formation-error data), kept for history. Superseded by `swarm/`. |
