"""One agent, one process, one MAVLink connection, one world model.

Run standalone: `python3 -m swarm.agent --id 0` (normally launched by
launch_swarm.py, one subprocess per agent id in config.AGENT_IDS).

Week 1 scope: connect to its own SITL instance, arm and take off, then at
LOOP_HZ read its own ground-truth position/velocity, broadcast it as a
StateEstimate, and fold received peer estimates into a local world model of
TrackedEntity objects that decay with age and get dropped once stale
(CLAUDE.md invariants #1, #2, #6, #7, #8).

Week 2 scope: each tick, run the world model + own state through
swarm/behaviors.py and swarm/arbiter.py to get a velocity command, send it
as SET_POSITION_TARGET_LOCAL_NED in GUIDED mode (CLAUDE.md's control loop
shape), and log per-tick metrics (order parameter, min neighbor distance,
whether the safety veto fired) via swarm/metrics.py.

Week 3 scope: each state broadcast now also carries "hears" — the sender's
own current set of heard peer ids — so every agent can locally reconstruct
the whole swarm's neighbor graph from gossip alone (no global state read,
invariant #2) and log its own estimate of algebraic connectivity (λ₂) via
swarm/graph.py.
"""
import argparse
import time

from pymavlink import mavutil

from . import arbiter, config, geo, graph, metrics
from .comms import Comms
from .state import DetectedBy, Kind, Source, StateEstimate, TrackedEntity


def log(agent_id, msg):
    print(f"[agent {agent_id}] {msg}", flush=True)


def latest(m, msg_type):
    """Drain the buffer, return the most recent message of this type."""
    msg = None
    while True:
        nxt = m.recv_match(type=msg_type, blocking=False)
        if nxt is None:
            return msg
        msg = nxt


def connect(agent_id):
    port = config.SITL_PORTS[agent_id]
    m = mavutil.mavlink_connection(f"tcp:127.0.0.1:{port}")
    m.wait_heartbeat()
    m.mav.request_data_stream_send(
        m.target_system, m.target_component,
        mavutil.mavlink.MAV_DATA_STREAM_ALL, config.LOOP_HZ * 2, 1)
    log(agent_id, f"connected on tcp:{port} (sys {m.target_system})")
    return m


def wait_ready(m, agent_id):
    start = time.time()
    while time.time() - start < config.READY_TIMEOUT_S:
        msg = m.recv_match(type="SYS_STATUS", blocking=True, timeout=2)
        if msg and msg.onboard_control_sensors_health & config.PREARM_OK:
            log(agent_id, "prearm checks passing")
            return True
    log(agent_id, f"not ready after {config.READY_TIMEOUT_S}s")
    return False


def arm_and_takeoff(m, agent_id):
    m.set_mode("GUIDED")
    time.sleep(1)

    armed_ok = False
    for attempt in range(1, config.ARM_RETRIES + 1):
        m.mav.command_long_send(
            m.target_system, m.target_component,
            mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM, 0, 1, 0, 0, 0, 0, 0, 0)

        deadline = time.time() + config.ARM_TIMEOUT_S
        while time.time() < deadline:
            msg = m.recv_match(type=["COMMAND_ACK", "STATUSTEXT"], blocking=True, timeout=1)
            if msg is None:
                continue
            if msg.get_type() == "STATUSTEXT":
                log(agent_id, msg.text)
            elif msg.command == mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM:
                armed_ok = msg.result == mavutil.mavlink.MAV_RESULT_ACCEPTED
                break
        if armed_ok:
            log(agent_id, f"arm accepted (attempt {attempt})")
            break
        log(agent_id, f"arm rejected (attempt {attempt}/{config.ARM_RETRIES}), retrying...")
        time.sleep(config.ARM_RETRY_INTERVAL_S)

    if not armed_ok:
        raise SystemExit(f"agent {agent_id} failed to arm after {config.ARM_RETRIES} attempts")

    m.mav.command_long_send(
        m.target_system, m.target_component,
        mavutil.mavlink.MAV_CMD_NAV_TAKEOFF, 0, 0, 0, 0, 0, 0, 0, config.TAKEOFF_ALT_M)
    log(agent_id, "taking off")

    deadline = time.time() + config.TAKEOFF_TIMEOUT_S
    while time.time() < deadline:
        pos = latest(m, "GLOBAL_POSITION_INT")
        alt = pos.relative_alt / 1000.0 if pos else 0.0
        if alt >= config.TAKEOFF_ALT_M * 0.95:
            log(agent_id, f"at altitude ({alt:.1f}m)")
            return
        time.sleep(1)
    raise SystemExit(f"agent {agent_id} did not reach altitude in time")


def own_state_estimate(pos_msg, now, origin):
    lat, lon = pos_msg.lat / 1e7, pos_msg.lon / 1e7
    n, e, d = geo.latlon_to_ned(origin["lat"], origin["lon"],
                                 lat, lon, pos_msg.relative_alt / 1000.0)
    vn, ve, vd = pos_msg.vx / 100.0, pos_msg.vy / 100.0, pos_msg.vz / 100.0
    return StateEstimate(
        position=(n, e, d),
        velocity=(vn, ve, vd),
        sigma_horizontal=0.0,
        sigma_vertical=0.0,
        timestamp=now,
        source=Source.GROUND_TRUTH,
        valid=True,
    )


def establish_origin(m, comms, agent_id):
    """Give every agent a shared local-NED reference frame.

    The origin provider freezes its own first GPS fix and re-broadcasts it
    every tick (cheap, and self-healing if a late/restarted agent missed the
    first message). Everyone else just waits for it. This is bootstrap
    plumbing, not a leadership role — see config.ORIGIN_PROVIDER_ID.
    """
    if agent_id == config.ORIGIN_PROVIDER_ID:
        pos = None
        while pos is None:
            pos = latest(m, "GLOBAL_POSITION_INT")
        origin = {"lat": pos.lat / 1e7, "lon": pos.lon / 1e7}
        log(agent_id, f"origin fixed at {origin}")
        return origin

    log(agent_id, "waiting for origin broadcast...")
    while True:
        for msg, _ in comms.receive():
            if msg.get("type") == "origin":
                origin = {"lat": msg["lat"], "lon": msg["lon"]}
                log(agent_id, f"origin received: {origin}")
                return origin
        time.sleep(0.1)


def run(agent_id):
    m = connect(agent_id)
    if not wait_ready(m, agent_id):
        raise SystemExit(f"agent {agent_id} never became ready")
    arm_and_takeoff(m, agent_id)

    comms = Comms(agent_id)
    origin = establish_origin(m, comms, agent_id)
    logger = metrics.MetricsLogger(agent_id)

    world_model = {}  # entity_id -> TrackedEntity
    heard_by = {}  # agent_id -> set(peer_ids that agent currently hears), from gossip
    my_state = None
    period = 1.0 / config.LOOP_HZ
    last_print = 0
    t_end = time.time() + config.RUN_DURATION_S

    while time.time() < t_end:
        tick_start = time.time()

        if agent_id == config.ORIGIN_PROVIDER_ID:
            comms.broadcast({"type": "origin", **origin})

        pos = latest(m, "GLOBAL_POSITION_INT")
        if pos is not None:
            now = time.time()
            my_state = own_state_estimate(pos, now, origin)
            comms.broadcast({
                "type": "state",
                "state": my_state.to_dict(),
                "hears": list(world_model.keys()),
            })

        for msg, rx_time in comms.receive():
            if msg.get("type") != "state":
                continue
            peer_id = msg["sender_id"]
            state = StateEstimate.from_dict(msg["state"])
            world_model[peer_id] = TrackedEntity(
                entity_id=peer_id,
                kind=Kind.PEER,
                state=state,
                last_seen=rx_time,
                detected_by=DetectedBy.RADIO,
                confidence=1.0,
            )
            heard_by[peer_id] = set(msg.get("hears", []))

        now = time.time()
        for eid in list(world_model.keys()):
            entity = world_model[eid]
            age = entity.age(now)
            if age > config.ENTITY_STALE_TIMEOUT_S:
                log(agent_id, f"dropping stale entity {eid} (age {age:.1f}s)")
                del world_model[eid]
                heard_by.pop(eid, None)
            else:
                entity.confidence = max(0.0, 1.0 - age / config.ENTITY_STALE_TIMEOUT_S)

        veto_reason = None
        if my_state is not None:
            heard_by[agent_id] = set(world_model.keys())

            velocity, veto_reason = arbiter.arbitrate(world_model, my_state)
            vn, ve, vd = velocity
            m.mav.set_position_target_local_ned_send(
                0, m.target_system, m.target_component,
                mavutil.mavlink.MAV_FRAME_LOCAL_NED, config.VELOCITY_TYPE_MASK,
                0, 0, 0, vn, ve, vd, 0, 0, 0, 0, 0)
            if veto_reason:
                log(agent_id, f"SAFETY VETO: {veto_reason}")

            phi = metrics.order_parameter(my_state, world_model)
            min_dist = metrics.min_neighbor_distance(my_state, world_model)
            lambda2 = graph.algebraic_connectivity(heard_by, config.AGENT_IDS)
            logger.log(phi, min_dist, lambda2, veto_reason)

        if now - last_print > 1.0:
            summary = ", ".join(
                f"{eid}: pos={e.state.position[:2]} age={e.age(now):.1f}s conf={e.confidence:.2f}"
                for eid, e in world_model.items()
            )
            log(agent_id, f"world model: {{{summary}}}" if summary else "world model: {}")
            last_print = now

        time.sleep(max(0.0, period - (time.time() - tick_start)))

    logger.close()
    comms.close()
    log(agent_id, "landing")
    m.set_mode("LAND")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--id", type=int, required=True, choices=config.AGENT_IDS)
    args = parser.parse_args()
    run(args.id)
