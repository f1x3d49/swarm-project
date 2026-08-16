# CLAUDE.md — Swarm Project

Project context for Claude Code. Read this before touching anything in this repo.

Companion document: `docs/ARCHITECTURE.md` — layer structure, interface specs,
noise models, and the expansion path. Read it before adding any new capability.

---

## 1. What this project is

An autonomous drone swarm research platform built at a Romanian military academy.
The research subject is **coordination, autonomy, and resilience** — how a group
of agents produces coherent collective behavior from local rules and degraded
communication.

**Scope boundary (non-negotiable):** no weapons, no payload integration, no
targeting. This project concerns flight coordination only. Do not propose,
design, or write code for anything outside that boundary.

### The goal in one sentence

The operator manually pilots one drone; the rest of the swarm perceives that drone
only as a local neighbor and reacts to its movement through emergent flocking —
not by tracking it as an assigned leader.

---

## 2. Primary deliverable: a live demo

The output of this project is a **live demonstration for the academy**, not a paper.
This drives every prioritization call. When in doubt, optimize in this order:

1. **It does not fail in front of an audience.** Robustness beats elegance.
2. **It is legible to a non-expert.** A viewer who has never heard of Reynolds
   must be able to see that something coordinated is happening.
3. **It resets fast.** One command to tear down and relaunch.
4. **It is rigorous underneath.** Metrics justify the demo; they do not replace it.

### Demo beats to design toward

- Operator flies a drone; the swarm visibly moves as a body in response.
- A node is killed mid-flight; the swarm heals and continues.
- Packet loss is dialed up live until the swarm visibly fragments.
- Live overlay of the order parameter so coherence is a number on screen.

Visualization (Gazebo or Mission Planner multi-vehicle map) is a **core
requirement**, not a stretch goal. Nothing is demo-ready until it can be seen.

---

## 3. Environment

- Windows host running **WSL2 / Ubuntu 22.04**. All project work happens inside WSL.
- **ArduPilot**, not PX4 — chosen for firmware consistency with the real hardware.
- Simulation: `sim_vehicle.py` (ArduPilot SITL), `pymavlink`, MAVProxy.
- Repo lives at `~/swarm-project`, under git.

### Known environment traps

- MAVProxy occupies **UDP 14550** by default. Use TCP ports instead:
  **5760 / 5770 / 5780** for instances 0 / 1 / 2. Launch with `--no-mavproxy`
  when driving SITL from scripts.
- MAVLink receive buffers go stale. Always drain to the newest message
  (the `latest()` helper) rather than reading the queue head.
- **Always restart SITL between experiments.** Carried-over state silently
  contaminates results. Never reuse a running instance to save time.

---

## 4. Architecture invariants

These are the rules that make this a swarm rather than a centralized controller
wearing a costume. Violating them invalidates every result.

1. **One process per agent.** Each agent owns its own MAVLink connection and its
   own local world model.
2. **No agent may read global state.** An agent knows only what has arrived
   through the comms layer, within its perception radius, recently enough to
   still be valid.
3. **The comms layer is an explicit, degradable component.** Packet loss,
   latency, range limits, and node death are parameters — not accidents.
4. **No script computes commands for more than one agent.** If a file reads all
   vehicle states and issues all commands, that is a bug. Flag it, do not build
   on it.
5. **The operator's drone is not special to the algorithm.** It is an informed
   agent that others perceive as an ordinary neighbor. Influence propagates
   through the neighbor graph. Do not add a privileged-leader shortcut.
6. **Never pass a bare position.** Every state estimate carries covariance, a
   measurement timestamp, a source, and a validity flag. See ARCHITECTURE.md §0.
7. **One world model.** Peers and obstacles are both tracked entities. Do not
   create a separate obstacle list. See ARCHITECTURE.md §0.
8. **Absence is information.** Entities decay with age and are dropped past a
   threshold. Never hold a stale position indefinitely.

### Control loop shape

Each agent, at 5–10 Hz: gather valid tracked entities → compute weighted sum of
active behaviors → arbitrate and apply safety veto → saturate to max speed →
send as a velocity setpoint via `SET_POSITION_TARGET_LOCAL_NED` in GUIDED mode.

---

## 5. Metrics

Logged to CSV per run, one run per experiment:

- **Order parameter (φ)** — magnitude of mean normalized velocity. How flocked.
- **Minimum inter-agent distance** — the safety margin.
- **Collision count.**
- **Algebraic connectivity (λ₂)** of the neighbor graph Laplacian — predicts
  the packet-loss threshold at which the swarm fragments.

---

## 6. Conventions

- **Full file contents, not patches.** When changing a file, output the whole
  updated file.
- **Reasoning before code.** Explain the approach and why, then implement.
- **One experiment per commit.** Commit messages state what was varied.
- Scripts are Python 3, `pymavlink`-based, runnable standalone from the repo root.
- Config (ports, sysids, gains, radii, noise parameters) lives in one place,
  never scattered as literals across agent files.
- New capability goes behind an existing interface. If it needs a new interface,
  stop and revisit ARCHITECTURE.md.

---

## 7. Current state

**Working:** SITL running 3 simultaneous instances. Scripted arm / takeoff /
telemetry / land via pymavlink. Leader–follower formation script with live CSV
logging of formation error.

**Known bug under investigation:** heading-dependent formation error traced to a
rotation sign error in the body-frame offset calculation. A speed sweep
(500 / 250 / 125 cm/s) ruled out velocity lag as the cause.

**Next up:** `StateEstimate` / `TrackedEntity` types, agent class with a
pluggable rule, then the degradable comms layer. Then Reynolds flocking with
3 agents. Then operator control of one agent.

---

## 8. Real hardware

Scope: **one real drone, validated against its simulated twin.** A single drone
cannot demonstrate a swarm, so the demo itself is the simulation. The real drone
is the credibility argument, not the centerpiece.

- **Flight controller: not yet chosen.** The SpeedyBee F405 V4 was considered
  and rejected — it stays on Betaflight as a separate FPV aircraft. Selection
  criteria are in ARCHITECTURE.md §6. Do not assume a board; ask.
- **Vehicle type also undecided.** Multirotor is the default assumption, but
  ArduPilot Rover is under consideration and would change nothing above the
  vehicle layer.
- **Requirement, not preference:** the board must have ≥2 MB flash so it runs
  full ArduPilot firmware rather than a reduced build. This is what killed the
  previous candidate.
- **GPS must include an integrated magnetometer.** Buy it integrated rather
  than solving the compass separately.
- **Regulatory:** outdoor flight falls under EASA / AACR (Romania). Multiple
  simultaneous autonomous aircraft is generally not open-category — another
  reason real-hardware scope stays at one vehicle. See ARCHITECTURE.md §7.

### What the swarm cannot currently sense

Peers are **announced, not sensed** — each agent broadcasts its own GPS position
over a shared telemetry link. Nothing perceives terrain, structures, wires,
people, or non-participating aircraft. Mitigation is procedural: open ground,
hard geofence, generous vertical separation. State this plainly rather than
letting anyone assume otherwise.

---

## 9. Reference algorithms

The implementation follows this literature. Cite it; don't reinvent it.

- **Reynolds (1987)** — separation, alignment, cohesion. The base rule set.
- **Couzin et al. (2005)** — informed minority steering an uninformed group.
  The theoretical justification for the operator-as-one-agent design.
- **Vicsek et al. (1995)** — order parameter and noise-induced phase transition.
  Source of the coherence metric.
- **Olfati-Saber (2006)** — rigorous flocking with stability proofs;
  alpha/beta/gamma agent framework. Used for the group-objective term.

**ArduPilot's built-in FOLLOW mode is a baseline, not the solution.** It tracks a
single sysid at a fixed offset and followers are blind to each other. Keep it
available for comparison; do not build the swarm on it.

---

## 10. Open items

- [ ] Demo date / deadline: _TBD — fill in_
- [ ] Solo or team project: _TBD — fill in_
- [ ] Choose visualization path (Gazebo vs Mission Planner multi-vehicle)
- [ ] Choose flight controller (≥2 MB flash — see ARCHITECTURE.md §6)
- [ ] Choose vehicle type (multirotor vs rover)
- [ ] Source GPS module with integrated magnetometer
- [ ] Source telemetry radio pair
