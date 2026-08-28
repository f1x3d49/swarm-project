"""Single source of truth for ports, ids, gains, radii, and timing.

Nothing outside this file should hardcode a port number, agent id, or timing
constant — see CLAUDE.md #6.
"""

# --- Agents -----------------------------------------------------------------
AGENT_IDS = [0, 1, 2]

# MAVLink TCP ports for the 3 SITL instances (CLAUDE.md known env trap: use
# TCP, not the MAVProxy-default UDP 14550).
SITL_PORTS = {0: 5760, 1: 5770, 2: 5780}

# Local UDP ports agents use to exchange StateEstimates with each other.
# Stage-0 comms (perfect delivery): each agent unicasts to every other
# agent's port to simulate a broadcast; see swarm/comms.py.
COMMS_PORTS = {0: 14700, 1: 14701, 2: 14702}

# Agent 0 is the one-time origin provider (see swarm/agent.py) purely to give
# every agent a shared local-NED reference frame — it carries no special
# authority in the swarm logic itself (CLAUDE.md invariant #5).
ORIGIN_PROVIDER_ID = 0

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
