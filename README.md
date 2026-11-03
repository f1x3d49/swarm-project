# Swarm Project — decentralized drone flocking in ArduPilot SITL

Three simulated ArduCopter drones fly as a flock using local rules only
(Reynolds separation / alignment / cohesion). A human pilots one of them with
the keyboard; the other two are never told who the pilot is — they see it as
an ordinary neighbor and follow it because flocking pulls them along.

Scope: flight coordination research only. No weapons, payloads, or targeting.

This branch (`handoff`) runs **natively on Windows** with Mission Planner on
the same PC — no WSL, no Linux, no ArduPilot build. Background reading:
[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) (design) and
[`CLAUDE.md`](CLAUDE.md) (rules and project status).

---

## What you will see

1. Three drones take off from the same spot and push apart. The terminal
   prints `SAFETY VETO: MIN_SEPARATION` for the first few seconds — expected.
2. Drones 0 and 2 fly toward a waypoint 40 m north / 40 m east, flocking as
   they go. Drone 1 is yours.
3. When you fly drone 1 with W/A/S/D, the other two bend toward it through
   cohesion and alignment. There is no leader-following code anywhere — the
   others only ever see drone 1 as a neighbor.
4. About 2 minutes after takeoff every drone switches to LAND on its own and
   writes a metrics CSV.

Each drone is controlled by its own Python process with its own MAVLink
connection and its own picture of the world. No process ever reads another
drone's state directly; everything a drone knows about its peers arrived
over the simulated radio link, and it forgets a peer that goes silent.

---

## Requirements

- Windows 10 or 11.
- **Mission Planner** (already installed).
- **Python 3.10 or newer** for Windows, from python.org or Anaconda. Check in
  a Command Prompt: `python --version`.
- Internet access once, to download the simulator.

## One-time setup

Open a Command Prompt in the repo folder (the one containing this README):

```bat
python -m pip install pymavlink numpy
python fetch_sitl.py
```

`fetch_sitl.py` downloads ArduPilot's official Windows ArduCopter simulator
(the same one Mission Planner's own *Simulation* screen uses) into
`sitl_bin\`, about 19 MB.

---

## Running it

You need three Command Prompt windows, **each opened in the repo folder**,
plus Mission Planner.

### 1. Mission Planner — open it first

Start Mission Planner and leave it on the *Flight Data* screen. Each drone
streams to it over UDP:

| Drone | Mission Planner UDP port | Shows up as |
|---|---|---|
| 0 | 14550 | system id 1 |
| 1 (yours) | 14551 | system id 2 |
| 2 | 14552 | system id 3 |

Set Mission Planner to listen on all three UDP ports (14550, 14551, 14552)
— one UDP connection per port. Each drone has its own system id, so
Mission Planner treats them as three separate vehicles on the map.

### 2. Window 1 — the simulators

```bat
python launch_sitl.py
```

Starts three simulator processes. Each one waits for its drone's controller
to connect before it starts simulating, so nothing appears in Mission Planner
yet. **Windows Firewall may ask about `ArduCopter.elf`** — allowing it on
private networks is fine; everything here stays on this PC.

### 3. Window 2 — the swarm

```bat
python launch_swarm.py
```

Starts one controller per drone. Each one connects to its simulator (the
drones appear in Mission Planner now), then waits for the simulated GPS to
settle. That takes **one to two minutes**, during which you'll see
`arm rejected ... Need Position Estimate` — that's normal. Then each drone
arms, takes off to 10 m and starts flocking. Every second each controller
prints what it knows about its neighbors:

```
[agent 0] world model: {1: pos=(12.3, 8.1) age=0.2s conf=0.96, 2: ...}
```

### 4. Window 3 — you fly drone 1

Once window 2 shows `[agent 1] OPERATOR agent ...`:

```bat
python operator_control.py
```

Keep this window focused and **hold** a key:

| Key | Action |
|---|---|
| W / S | fly drone 1 north / south at 3 m/s |
| A / D | fly drone 1 west / east |
| no key for 0.5 s | drone 1 hovers |
| Q | quit (drone 1 hovers but stays in the flock) |

Try holding **D** for 10–15 seconds: drone 1 breaks east, and the other two
curve after it.

### Stopping and running again

- The controllers land the drones and exit by themselves about 2 minutes
  after takeoff. Ctrl+C in window 2 stops them early.
- Then press **Ctrl+C in window 1** to stop the simulators.
- **Always restart window 1 before another run** — each launch starts the
  simulators from a clean state.

### Optional — kill a drone mid-flight

Window 2 prints each controller's PID at startup. In another Command Prompt:

```bat
taskkill /F /PID <pid>
```

The survivors stop hearing from it, forget it after 5 s (`dropping stale
entity ...`) and carry on as a two-drone flock. The killed drone's simulator
keeps it hovering in place.

---

## Reading the results

Each controller writes `metrics_agent<id>_<HHMMSS>.csv` in the repo folder,
computed only from that drone's own view of the world:

| Column | Meaning |
|---|---|
| `t` | seconds since that drone started flocking |
| `phi` | order parameter (Vicsek 1995): 1.0 = all headings aligned, 0 = none |
| `min_neighbor_dist_m` | distance to the nearest peer this drone can see |
| `lambda2` | algebraic connectivity of the neighbor graph: 3.0 = all three linked, 0 = split apart |
| `veto` | `MIN_SEPARATION` or `GEOFENCE` when the safety layer overrode the flocking that tick |

`metrics_agent*_004553.csv` / `metrics_agent2_004554.csv` in the repo are a
reference run recorded by the author with the operator flying drone 1: φ ends
at about 0.99 for all three drones and λ₂ stays at 3.0.

Quick plot (needs `python -m pip install matplotlib`):

```bat
python -c "import csv,sys,matplotlib.pyplot as plt; [plt.plot([float(r['t']) for r in csv.DictReader(open(f))],[float(r['phi']) for r in csv.DictReader(open(f))],label=f) for f in sys.argv[1:]]; plt.xlabel('t (s)'); plt.ylabel('phi'); plt.legend(); plt.show()" metrics_agent0_004553.csv metrics_agent1_004553.csv metrics_agent2_004554.csv
```

---

## Things that look like bugs but are expected

- **`SAFETY VETO: MIN_SEPARATION` at startup, and `min_neighbor_dist_m` of
  0.0.** All three simulators start at the same spot. The veto pushes them
  apart.
- **`phi` is 0 in the first rows.** Hovering drones have no heading.
- **Drone 1 just hovers** if `operator_control.py` isn't running. It still
  flocks with its neighbors; it just has no destination of its own.
- **The map is in Canberra, Australia.** That's ArduPilot's standard
  simulator location (`SITL_HOME` in `swarm/config.py`).

## Troubleshooting

| Symptom | Fix |
|---|---|
| `ArduCopter.elf not found` | Run `python fetch_sitl.py`. |
| `no simulator on tcp:5760 after 60s` | Window 1 isn't running, or a simulator crashed — see `sitl_logs\<n>\sitl.log`. |
| A controller stuck on `waiting for origin broadcast...` | Drone 0's controller failed — read its messages in window 2. Restart windows 1 and 2. |
| Drone 0 shows in Mission Planner but 1 and 2 don't | Add the UDP 14551 / 14552 connections (step 1). |
| Keys do nothing | Click on window 3 so it has keyboard focus. |
| Errors about ports already in use | A previous run is still alive. Close all three windows (or end `python.exe` / `ArduCopter.elf` in Task Manager) and start over. |

---

## Honest limitations

- **Peers are announced, not sensed.** Each drone broadcasts its own
  simulated GPS position. Nothing perceives terrain, structures, people, or
  other aircraft.
- **Comms are perfect.** Packet loss, latency, and range limits are designed
  (`docs/ARCHITECTURE.md` §3) but not built yet.
- **Positions are exact simulator truth.** There is no GPS noise model yet.
- **The 2 m separation floor is reactive, not a guarantee.** In the
  reference run the closest approach after the initial spread was 0.8 m — the
  veto fired and pushed the drones apart, but only after the floor was
  crossed. Simulated drones don't physically collide, so this only shows up in
  the CSV.
- **A killed drone becomes invisible, not avoided.** Survivors forget it,
  but its simulator still has it hovering at flock altitude.
- **The safety layer covers the geofence (60 m) and separation only.**
  Battery, lost-link and altitude limits aren't built.

---

## Repo map

| Path | What |
|---|---|
| `fetch_sitl.py` | One-time download of the Windows simulator |
| `sitl_params/` | Extra simulator parameters (telemetry rates toward Mission Planner) |
| `launch_sitl.py`, `launch_swarm.py`, `operator_control.py` | The three windows above |
| `swarm/config.py` | Every port, gain, radius, and timeout |
| `swarm/agent.py` | One drone's controller: connect, take off, 5 Hz sense → decide → act loop |
| `swarm/state.py` | `StateEstimate` / `TrackedEntity`: positions always carry uncertainty, time, source, validity |
| `swarm/comms.py` | Drone-to-drone messaging (currently perfect delivery over local UDP) |
| `swarm/behaviors.py` | Separation, alignment, cohesion, waypoint, operator input |
| `swarm/arbiter.py` | Weighted blend, speed limit, safety veto |
| `swarm/metrics.py`, `swarm/graph.py` | φ, min distance, λ₂, CSV logging |
| `swarm/operator_link.py` | Keyboard → drone 1 channel (never seen by the other drones) |
| `first_flight.py`, `swarm_takeoff.py`, `formation.py`, `live_view.py`, `notes.md`, `formation_*.csv` | An earlier leader–follower phase, kept for history. Linux-only; not part of this demo. |

### How this differs from the `main` branch

`main` runs under WSL2 with a source build of ArduPilot, and puts a MAVProxy
relay in front of each simulator to feed both the controller and a Mission
Planner on another PC. Here each simulator is ArduPilot's prebuilt Windows
binary, started directly: the controller connects to its TCP port 5760/5770/
5780, and the simulator's second serial port pushes straight to Mission
Planner on UDP 14550/14551/14552. The swarm logic itself (`swarm/` apart from
`config.py` and the connection in `agent.py`) is identical.
