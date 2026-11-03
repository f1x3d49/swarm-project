"""Single source of truth for ports, ids, gains, radii, and timing.

Nothing outside this file should hardcode a port number, agent id, or timing
constant — see CLAUDE.md #6.
"""

# --- Agents -----------------------------------------------------------------
AGENT_IDS = [0, 1, 2]

# --- Simulator (handoff branch: native Windows, no WSL, no MAVProxy) -------
# launch_sitl.py starts the ArduCopter SITL binary directly, one per agent.
# Each instance exposes MAVLink on two serial ports, so the one-client-per-port
# limit (CLAUDE.md "known environment traps") is met without a MAVProxy relay:
#
#   SERIAL0 -> TCP SITL_PORTS[n]: this agent's own connection (agent.py).
#              The instance waits for a client here before it starts.
#   SERIAL1 -> UDP push to MISSION_PLANNER_HOST:MISSION_PLANNER_PORTS[n], the
#              same ports the MAVProxy --out used on main, so Mission Planner
#              is set up the same way. Two-way: MP can still command.
SITL_PORTS = {0: 5760, 1: 5770, 2: 5780}

# Mission Planner runs on the same Windows PC as the simulators.
MISSION_PLANNER_HOST = "127.0.0.1"
MISSION_PLANNER_PORTS = {0: 14550, 1: 14551, 2: 14552}

# Each instance gets its own MAVLink system id (n+1) so Mission Planner shows
# three distinct vehicles rather than merging them.
SITL_SYSIDS = {0: 1, 1: 2, 2: 3}

# Where every instance starts: lat, lon, alt (m AMSL), heading. This is
# ArduPilot's standard SITL home (CMAC, Canberra). All three start on the same
# spot; the separation veto pushes them apart in the first seconds.
SITL_HOME = "-35.363261,149.165230,584,353"

# Windows simulator binary + its Cygwin DLLs + copter defaults, downloaded by
# fetch_sitl.py into this folder (relative to the repo root).
SITL_BIN_DIR = "sitl_bin"
SITL_WINDOWS_EXE = "ArduCopter.elf"  # a Windows .exe despite the name (Cygwin build)
SITL_DEFAULTS_FILE = "copter.parm"
# Extra parameter defaults applied after copter.parm, kept in the repo:
# telemetry rates on the Mission Planner port, so the map gets positions
# even if Mission Planner never requests a stream itself.
SITL_EXTRA_DEFAULTS = ["sitl_params/mission_planner_streams.parm"]
# On Linux (only used to test this branch from WSL), launch_sitl.py falls back
# to a locally built ArduPilot instead of the Windows binary.
SITL_LINUX_BINARY = "~/ardupilot/build/sitl/bin/arducopter"

# How long agent.py keeps retrying its TCP connection while the simulator
# boots, so launch order and timing between terminals don't matter.
CONNECT_TIMEOUT_S = 60

# Local UDP ports agents use to exchange StateEstimates with each other.
# Stage-0 comms (perfect delivery): each agent unicasts to every other
# agent's port to simulate a broadcast; see swarm/comms.py.
COMMS_PORTS = {0: 14700, 1: 14701, 2: 14702}

# Agent 0 is the one-time origin provider (see swarm/agent.py) purely to give
# every agent a shared local-NED reference frame — it carries no special
# authority in the swarm logic itself (CLAUDE.md invariant #5).
ORIGIN_PROVIDER_ID = 0

# Which agent a human operator flies (week 4: docs/ARCHITECTURE.md's
# operator-control step). This agent swaps group_objective for live input
# from operator_control.py (see swarm/behaviors.py's operator_input) but is
# otherwise an ordinary agent — every peer still only ever sees a normal
# StateEstimate broadcast from it (CLAUDE.md invariant #5: no leader
# shortcut, no special-casing in peers' behavior code).
OPERATOR_AGENT_ID = 1

# Local UDP port operator_control.py sends commanded velocity to. Separate
# from COMMS_PORTS (that's inter-agent gossip; this is a one-way human ->
# operator-agent channel, never relayed to peers).
OPERATOR_INPUT_PORT = 14800
# If no fresh command arrives within this window, the operator behavior
# reports zero velocity (hover) rather than the last-known command — a
# crashed or closed operator_control.py must fail safe, not fly off on a
# stale command. Tighter than ENTITY_STALE_TIMEOUT_S because this is live
# human control, not gossip about a peer's position.
OPERATOR_INPUT_STALE_TIMEOUT_S = 1.0
W_OPERATOR_INPUT = 2.0

# --- Timing -------------------------------------------------------------
LOOP_HZ = 5
PREARM_OK = 1 << 28  # bit 28 of SYS_STATUS sensor health = prearm checks passing

# An entity's confidence decays linearly to 0 over this window, and is
# dropped from the world model once its age exceeds it (CLAUDE.md #8).
ENTITY_STALE_TIMEOUT_S = 5.0

# --- Flight -------------------------------------------------------------
TAKEOFF_ALT_M = 10.0
TAKEOFF_TIMEOUT_S = 60
ARM_TIMEOUT_S = 5
# SITL rejects arming ("Need Position Estimate") until its EKF has converged,
# which takes ~60-90 s of simulated time. On this branch each simulator only
# starts when its agent connects, so the agent itself has to sit through that
# warm-up: 45 attempts at ~2-3 s each gives it about 2 minutes.
ARM_RETRIES = 45
ARM_RETRY_INTERVAL_S = 2
READY_TIMEOUT_S = 120

RUN_DURATION_S = 120

# MAVLink SET_POSITION_TARGET_LOCAL_NED type_mask: use velocity only, ignore
# position, acceleration, yaw and yaw rate. Frame is MAV_FRAME_LOCAL_NED,
# which is oriented North-East-Down regardless of the vehicle's own EKF
# origin — so a velocity vector computed in swarm/agent.py's shared world
# frame is valid to send as-is, with no origin-offset translation needed.
VELOCITY_TYPE_MASK = 0b0000111111000111

# --- Behaviors (week 2: docs/ARCHITECTURE.md §5) -------------------------
# Neighbors farther than this are outside cohesion/alignment sensing range.
NEIGHBOR_RADIUS_M = 30.0
# Neighbors closer than this trigger the (soft, weighted) separation rule.
SEPARATION_RADIUS_M = 5.0
MAX_SPEED_MPS = 3.0

W_SEPARATION = 3.0
W_ALIGNMENT = 1.0
W_COHESION = 1.0
W_GROUP_OBJECTIVE = 1.5

# Scripted group objective for week 2 (stands in for operator control until
# week 4): a fixed waypoint in the shared NED frame, meters from the origin.
GROUP_OBJECTIVE_TARGET_NED = (40.0, 40.0, 0.0)

# --- Safety veto (docs/ARCHITECTURE.md §5) --------------------------------
# Hard floor: closer than this and the arbiter overrides every behavior with
# a direct repulsion command. Built now, before it's load-bearing, per
# ARCHITECTURE.md — "the difference between a demo that fails safely and a
# demo that fails memorably." Must stay tighter than SEPARATION_RADIUS_M so
# the soft separation rule gets a chance to act first.
MIN_SEPARATION_M = 2.0
# Hard radius from the shared origin; crossing it overrides every behavior
# with a direct return-to-origin command.
GEOFENCE_RADIUS_M = 60.0
