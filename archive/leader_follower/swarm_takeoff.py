from pymavlink import mavutil
import time

PORTS = [5760, 5770, 5780]
ALTITUDES = [10, 15, 20]
PREARM_OK = 1 << 28          # bit 28 of sensor health = pre-arm checks passing

def connect(port, idx):
    m = mavutil.mavlink_connection(f'tcp:127.0.0.1:{port}')
    m.wait_heartbeat()
    print(f"drone {idx} connected (sys {m.target_system})")
    # MAVProxy used to request these for us
    m.mav.request_data_stream_send(
        m.target_system, m.target_component,
        mavutil.mavlink.MAV_DATA_STREAM_ALL, 4, 1)
    return m

def wait_ready(m, idx, timeout=120):
    start, last = time.time(), ""
    while time.time() - start < timeout:
        msg = m.recv_match(type=['SYS_STATUS', 'STATUSTEXT'],
                           blocking=True, timeout=2)
        if msg is None:
            continue
        if msg.get_type() == 'STATUSTEXT':
            if msg.text != last:
                print(f"  [{idx}] {msg.text}")
                last = msg.text
        elif msg.onboard_control_sensors_health & PREARM_OK:
            print(f"drone {idx} ready to arm")
            return True
    print(f"drone {idx} still not ready after {timeout}s")
    return False

def arm(m, idx):
    m.set_mode('GUIDED')
    time.sleep(1)
    m.mav.command_long_send(
        m.target_system, m.target_component,
        mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM,
        0, 1, 0, 0, 0, 0, 0, 0)
    deadline = time.time() + 5
    while time.time() < deadline:
        ack = m.recv_match(type='COMMAND_ACK', blocking=True, timeout=1)
        if ack and ack.command == mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM:
            ok = ack.result == mavutil.mavlink.MAV_RESULT_ACCEPTED
            print(f"drone {idx} arm {'accepted' if ok else f'REJECTED (result {ack.result})'}")
            return ok
    print(f"drone {idx} arm command got no response")
    return False

drones = [connect(p, i) for i, p in enumerate(PORTS)]

for i, m in enumerate(drones):
    wait_ready(m, i)

armed = [arm(m, i) for i, m in enumerate(drones)]
if not all(armed):
    print("not all drones armed — stopping")
    raise SystemExit

def latest(m, msg_type):
    """Drain the buffer, return the most recent message of this type."""
    msg = None
    while True:
        nxt = m.recv_match(type=msg_type, blocking=False)
        if nxt is None:
            return msg
        msg = nxt

print("takeoff")
for i, m in enumerate(drones):
    m.mav.command_long_send(
        m.target_system, m.target_component,
        mavutil.mavlink.MAV_CMD_NAV_TAKEOFF,
        0, 0, 0, 0, 0, 0, 0, ALTITUDES[i])

# Flush stale telemetry queued during the arming phase
time.sleep(0.5)
for m in drones:
    latest(m, 'GLOBAL_POSITION_INT')

deadline = time.time() + 60
while time.time() < deadline:
    alts = []
    for m in drones:
        msg = latest(m, 'GLOBAL_POSITION_INT')
        alts.append(round(msg.relative_alt / 1000.0, 1) if msg else None)
    print(f"altitudes: {alts}")
    if all(a is not None and a >= t * 0.95 for a, t in zip(alts, ALTITUDES)):
        print("all drones at target altitude")
        break
    time.sleep(1)

print("holding 5s")
time.sleep(5)

print("landing")
for m in drones:
    m.set_mode('LAND')