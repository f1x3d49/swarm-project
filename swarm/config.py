"""Single source of truth for ports, ids, gains, radii, and timing.

Nothing outside this file should hardcode a port number, agent id, or timing
constant — see CLAUDE.md #6.
"""

# --- Agents -----------------------------------------------------------------
AGENT_IDS = [0, 1, 2]

# Raw MAVLink TCP port each SITL instance serves. Only one real client can
# attach to this port at a time (verified empirically — a second TCP
# connection accepts at the socket level but never receives data), so as of
# week 3 nothing connects here directly. It's the --master target MAVProxy
# uses; kept here as the single source of truth for the sim_vehicle.py launch
# commands (see docs/ARCHITECTURE.md's Mission Planner section).
SITL_PORTS = {0: 5760, 1: 5770, 2: 5780}

# Local UDP relay port each agent.py process connects to instead of
# SITL_PORTS directly (week 3 change — see CLAUDE.md "known environment
# traps"). MAVProxy sits in front of each SITL instance now, fed by
# --out=udp:127.0.0.1:<this port>, so it can fan the same MAVLink stream out
# to a second consumer: Mission Planner on a remote PC, via MISSION_PLANNER_PORTS.
AGENT_LOCAL_MAVLINK_PORTS = {0: 6760, 1: 6770, 2: 6780}

# UDP ports on the remote Mission Planner PC that each instance's MAVProxy
# pushes telemetry/commands to (an --out target, not a listener here — so no
# inbound firewall rule is needed on this machine).
MISSION_PLANNER_PORTS = {0: 14550, 1: 14551, 2: 14552}

# LAN IP of the PC running Mission Planner (David's home network — this dev
# machine is org-managed and can't have MP installed on it, see CLAUDE.md
# "known environment traps"). Environment-specific and likely to change
# (different network, different PC) — this is the one place to update it;
# launch_sitl.py reads it from here to build the sim_vehicle.py commands.
MISSION_PLANNER_HOST = "192.168.1.135"

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
ARM_RETRIES = 8  # SITL commonly rejects arming for a few seconds after prearm goes green
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
