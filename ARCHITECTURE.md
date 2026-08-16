# ARCHITECTURE.md — Layers, Seams, and the Expansion Path

Companion to `CLAUDE.md`. That file states the rules. This one explains the
structure they protect, and where future capability plugs in.

**Read this before adding any new capability.** The point of this document is
that object detection, GPS denial, jamming resilience, object recognition, and
tactics are all *already accounted for* as implementations behind existing
interfaces. If adding one of them requires changing the interfaces, stop and
reconsider the design.

---

## 0. The forward-compatibility rules

Two decisions cost almost nothing now and are expensive to retrofit. They are
binding.

### Rule A — Every state estimate carries uncertainty and validity

No component ever passes a bare position. The unit of exchange is:

```
StateEstimate:
    position        # local NED, meters
    velocity        # m/s
    covariance      # 3x3, or at minimum (sigma_horizontal, sigma_vertical)
    timestamp       # when measured, not when received
    source          # GPS | FLOW | UWB | VISION | DEAD_RECKON | GROUND_TRUTH
    valid           # bool
```

Why this matters: GPS loss becomes `valid=False`. Jamming becomes covariance
growing without bound. Sensor fusion becomes a weighted combination that already
has weights. Stale data becomes a timestamp comparison. None of these require a
new interface.

### Rule B — One world model, not separate peer and obstacle lists

An agent holds a single collection of **tracked entities**:

```
TrackedEntity:
    entity_id
    kind            # PEER | OBSTACLE | UNKNOWN | AIRCRAFT
    state           # StateEstimate
    last_seen
    detected_by     # RADIO | PROXIMITY | VISION
    class_label     # optional, populated by recognition later
    confidence      # optional
```

A peer heard over radio and a tree seen by a rangefinder are the same shape to
the behavior layer. This is what makes perception additive instead of surgical.

**Absence is information.** An entity that stops being heard from does not
persist at its last position forever. It decays: confidence falls with age, and
past a threshold it is dropped. A silent neighbor is a neighbor that might be
anywhere.

---

## 1. The layer stack

```
   ┌─────────────────────────────────────────┐
   │  TACTICS         policy over behaviors  │
   ├─────────────────────────────────────────┤
   │  BEHAVIORS       world model → velocity │
   ├─────────────────────────────────────────┤
   │  ARBITER         blend + SAFETY VETO    │
   ├─────────────────────────────────────────┤
   │  WORLD MODEL     tracked entities       │
   ├──────────────┬──────────────┬───────────┤
   │ LOCALIZATION │    COMMS     │ PERCEPTION│
   │  where am I  │ what do peers│  what else│
   │              │   tell me    │  is there │
   ├──────────────┴──────────────┴───────────┤
   │  VEHICLE         MAVLink → ArduPilot    │
   └─────────────────────────────────────────┘
```

Each of the three input layers is an interface with a swappable implementation.
Today each has exactly one trivial implementation. That is correct — do not
build the others speculatively. Build the seam, not the plugin.

---

## 2. LOCALIZATION — "where am I?"

**Interface:** `get_state() -> StateEstimate`

| Stage | Implementation | Status |
|---|---|---|
| 0 | SITL ground truth | current |
| 1 | GPS with realistic noise | **next** |
| 2 | GPS degradation and dropout | planned |
| 3 | GPS denial with fallback (flow / UWB / dead reckoning) | future |

### The GPS noise model (stage 1 spec)

Do not model GPS error as white noise. White noise filters out trivially and
makes the problem look far easier than it is. Real GNSS error is dominated by a
**slowly varying bias** — same satellites, same atmosphere, drifting over tens
of seconds.

Model error as two components:

```
error_agent = common_mode(t) + independent_agent(t)
```

- **`common_mode(t)`** — shared by all agents in the swarm. First-order
  Gauss-Markov process, correlation time on the order of 60–120 s, horizontal
  sigma ≈ 1.5–2.5 m. This is the component that **cancels when you subtract two
  agent positions**, which is why relative accuracy between nearby drones is
  much better than absolute accuracy. It is also the principle behind
  differential GNSS.
- **`independent_agent(t)`** — per-agent, shorter correlation time (≈ 5–20 s),
  horizontal sigma ≈ 0.5–1.5 m. This is the component that actually threatens
  inter-agent separation.

Vertical error runs roughly 1.5–3× horizontal. Update rate 5–10 Hz with
latency of 100–200 ms before the value is usable by a neighbor.

These numbers are reasonable engineering defaults, not measurements. Calibrate
them against logs from the real drone once it is flying — that comparison is
itself a sim-to-real result worth reporting.

### The experiment this enables

Sweep commanded separation distance against noise level; find where minimum
inter-agent distance crosses zero and collisions begin. Output: a defensible
**minimum safe separation** for real flight, derived in simulation. This is the
single most valuable near-term experiment in the project.

---

## 3. COMMS — "what do peers tell me?"

**Interface:** `broadcast(msg)` / `receive() -> [(msg, rx_time)]`

Messages carry the sender's id, its own `StateEstimate` (including that
agent's uncertainty), and a send timestamp. A jammed or degraded agent
therefore advertises its own degradation — neighbors know its data is
untrustworthy rather than silently using it.

| Stage | Implementation | Status |
|---|---|---|
| 0 | Perfect delivery | current |
| 1 | Packet loss, latency, range limit | **next** |
| 2 | Node death, network partition | planned |
| 3 | Denial (jamming) — spatial and channel-wide | future |
| 4 | Spoofed / implausible messages | future |

### Denial and spoofing — research framing

This is **resilience research**: the object of study is how a swarm degrades and
recovers when its links are denied. The simulator models the *effect* of denial
on the receiving system. It does not model or describe how to produce denial,
and this project does not build transmitting hardware.

Two denial models worth implementing:

- **Spatial** — a denial source at a position with a radius. Agents inside lose
  links, or lose GNSS validity, or both. This produces the good demo moment:
  the swarm flies through a dead zone and reforms on the far side.
- **Channel-wide** — global loss probability ramped continuously. Sweep it and
  find the fragmentation threshold. Compare against the predicted collapse of
  algebraic connectivity λ₂.

Spoofing is the most interesting resilience question and the hardest: a peer
reports a plausible but wrong position. Detection relies on cross-checks —
kinematic feasibility (did it move faster than physically possible?), agreement
between neighbors, and consistency with independent range measurement. Treat
this as a later research question, not an early build item.

### Real-hardware constraint to respect

On real aircraft, peer positions arrive over a **shared radio channel**. A SiK
radio at 57600 baud carries a finite number of position updates per second
across the whole swarm. Bandwidth caps swarm size long before the algorithm
does. Model the channel as having a capacity, and measure where it saturates —
this is a real, quotable constraint.

---

## 4. PERCEPTION — "what else is out there?"

**Interface:** `detect() -> [Detection]`, where a `Detection` is a bearing,
range, uncertainty, and optionally a class label and confidence.

| Stage | Implementation | Status |
|---|---|---|
| 0 | Null — the world is empty | current |
| 1 | Simulated obstacles from the sim world | planned |
| 2 | Rangefinder / proximity sensor | future |
| 3 | Camera + object recognition on a companion computer | future |

**This is the layer that does not exist today, and its absence is honest.**
Currently the swarm cannot see terrain, structures, wires, people, or
non-participating aircraft. The mitigation is procedural, not technical: fly in
open ground, hard geofence, generous vertical separation between agents.
Say this plainly in the demo rather than letting anyone assume otherwise.

Detections feed the world model as `TrackedEntity` with `kind=OBSTACLE`. The
behavior layer's separation rule then applies to them with no modification —
which is the payoff of Rule B.

Note that ArduPilot has its own proximity and object-avoidance support
(rangefinders, BendyRuler, Dijkstra path planning). Where firmware avoidance
overlaps with swarm-level avoidance, **firmware wins** — it runs faster and
closer to the actuators. Swarm-level logic handles intent; firmware handles
reflexes.

---

## 5. BEHAVIORS and TACTICS

**Behavior interface:** `(world_model, self_state) -> (desired_velocity, weight)`

Behaviors are pure functions. They read the world model and return a desired
velocity with a weight. They never talk to MAVLink and never know about each
other.

Current: separation, alignment, cohesion, group objective.

Later behaviors slot in unchanged: obstacle avoidance, altitude keeping,
return-on-comms-loss, station keeping, area coverage, dispersal, regroup.

**Tactics are a policy over behavior weights** — a state machine whose states
are named postures (transit, search, disperse, regroup, recover) and whose
transitions fire on world-model conditions (link quality dropped, entity
detected, agent count fell, geofence approached). Tactics never compute
velocities directly. They only re-weight behaviors and set the group objective.

This keeps tactics entirely separable from flight code, which means they can be
developed and tested without touching anything that flies.

**Scope reminder:** tactics here means coordination and maneuver — formation,
search, coverage, dispersal, recovery. The project's no-weapons, no-payload
boundary applies to this layer as much as any other.

### ARBITER and the safety veto

Below behaviors sits an arbiter that blends weighted outputs, saturates to max
speed, and then applies a **safety veto** that no behavior can override:

- geofence
- minimum separation floor
- battery floor
- comms-loss failsafe
- altitude limits

Build the veto early, before it is needed. It is the difference between a demo
that fails safely and a demo that fails memorably.

---

## 6. Hardware selection criteria

**No board has been chosen. Do not assume one — ask.**

The SpeedyBee F405 V4 was evaluated and rejected. It remains a Betaflight FPV
aircraft and is out of scope for this project. The reasoning behind that
rejection is preserved here because it defines what the replacement must have.

### Hard requirement: ≥2 MB flash

ArduPilot's full firmware exceeds 1 MB. Boards below that get an automatically
**reduced build** with features silently omitted. Consequences that bit the
previous candidate:

- **Lua scripting requires 2 MB and is unavailable on F4-class boards entirely.**
- Feature availability varies per board and per release. The definitive list is
  the `features.txt` file in that board's folder on the firmware server —
  check it before assuming any capability exists.

H743-class boards (STM32H743, 480 MHz, 2 MB flash) clear this comfortably and
are the mainstream ArduPilot choice. F722 is a middle ground that buys a second
compromise for the same reason the first was rejected — avoid it.

### Other selection criteria

- **UART count** is the practical constraint, not processing power. Budget for
  GPS, telemetry radio, RC receiver, and at least one spare for a companion
  computer later. Four minimum; more is better.
- **SD card storage** — needed for Lua scripts and proper logging. Some
  FPV-oriented H7 boards use onboard flash instead. Verify before buying.
- **Board variants with similar names differ substantially.** Confirm the exact
  variant against its ArduPilot documentation page.

### Vehicle type is also open

Multirotor is the default assumption. **ArduPilot Rover is a live alternative**
and changes nothing above the vehicle layer — same MAVLink, same GUIDED
velocity commands, behaviors drop from 3D to 2D. Trade-offs:

- Rovers are cheaper per unit, survive their own failures, and fall entirely
  outside aviation regulation — which makes *multiple real vehicles* affordable
  and legal, turning the demo from simulation-plus-one-drone into a genuine
  physical swarm.
- GPS error does not shrink on the ground, so rovers need the same generous
  separation as aircraft, and indoor operation is off the table without
  non-GNSS positioning.

### Independent of board choice

- Stages 2–3 of PERCEPTION require a **companion computer** (Raspberry Pi Zero
  2 W, Orange Pi, Jetson Orin Nano) running perception and swarm logic, talking
  MAVLink to the flight controller. The FC flies; the companion thinks. No
  flight controller of any class does onboard vision.
- **GPS module must include an integrated magnetometer.**
- Each vehicle needs its own telemetry radio; peer position sharing depends on
  it. Radios must share a network id.
- The flight controller is roughly a quarter of the build cost. Frame, motors,
  ESC, props, batteries, RC link, GPS, and radios are the rest.

### Schedule warning

A first ArduPilot build is not a weekend. Assembly, parameter setup, compass
calibration, tuning, and getting GUIDED mode reliable is realistically weeks of
intermittent work, and most of its failures will have nothing to do with the
research. **Sequence the build after the simulated demo runs end to end**, so a
slipping build cannot take the deliverable down with it.

---

## 7. Regulatory ceiling

Flying a single drone is straightforward. Flying **multiple autonomous aircraft
simultaneously** is generally not an open-category activity under EASA rules —
it points toward specific-category authorisation and a SORA risk assessment,
which is a substantial administrative undertaking with AACR.

This is a strong argument for keeping the real-hardware scope at one drone and
demonstrating the swarm in simulation. Verify current requirements with AACR
before planning any outdoor multi-aircraft flight; do not rely on this summary.

---

## 8. Build order

Each step is usable on its own. Do not skip ahead.

1. `StateEstimate` and `TrackedEntity` types. Agent class with a pluggable rule.
2. Comms layer, perfect delivery, with the degradation knobs stubbed at zero.
3. Reynolds flocking, 3 agents, scripted group objective.
4. Visualization. Nothing is demo-ready until it can be seen.
5. Operator control of one agent.
6. Comms degradation: loss, latency, range. Node kill.
7. GPS noise model. Separation sweep. Minimum safe separation result.
8. Safety veto layer.
9. Real drone: flash ArduPilot, fly the twin, calibrate the noise model.

Everything in sections 2–5 marked "future" comes after the demo exists.
The demo is the deliverable; the architecture is what keeps the demo from
becoming a dead end.
