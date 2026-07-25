from pymavlink import mavutil
import time, math, csv, sys
from datetime import datetime

PORTS   = [5760, 5770, 5780]
ALT     = 10.0
OFFSETS = [(0, 0), (12, -10), (12, 10)]   # (along, lateral) — behind & to the side, in leader's body frame
SQUARE  = 40.0                             # side length of leader's path
LOOP_HZ = 5

SPEED    = int(sys.argv[1]) if len(sys.argv) > 1 else 500   # cm/s
DURATION = 90
LOGFILE  = f"formation_{SPEED}_{datetime.now():%H%M%S}.csv"

PREARM_OK = 1 << 28
FRAME     = mavutil.mavlink.MAV_FRAME_GLOBAL_RELATIVE_ALT_INT
TYPE_MASK = 0b0000111111111000               # position only

def latest(m, msg_type):
    """Drain the buffer, return the most recent message of this type."""
    msg = None
    while True:
        nxt = m.recv_match(type=msg_type, blocking=False)
        if nxt is None:
            return msg
        msg = nxt

def offset_latlon(lat, lon, dn, de):
    return lat + dn / 111320.0, lon + de / (111320.0 * math.cos(math.radians(lat)))

def dist_m(lat1, lon1, lat2, lon2):
    dn = (lat2 - lat1) * 111320.0
    de = (lon2 - lon1) * 111320.0 * math.cos(math.radians(lat1))
    return math.hypot(dn, de)

def rotate_offset(heading_deg, along, lateral):
    """along = distance behind leader (+), lateral = distance to the side (+ = right).
       Returns (north, east) displacement in world frame."""
    h = math.radians(heading_deg)
    dn = -along * math.cos(h) - lateral * math.sin(h)
    de = -along * math.sin(h) + lateral * math.cos(h)
    return dn, de

def goto(m, lat, lon, alt):
    m.mav.set_position_target_global_int_send(
        0, m.target_system, m.target_component, FRAME, TYPE_MASK,
        int(lat * 1e7), int(lon * 1e7), alt,
        0, 0, 0, 0, 0, 0, 0, 0)

def connect(port, idx):
    m = mavutil.mavlink_connection(f'tcp:127.0.0.1:{port}')
    m.wait_heartbeat()
    m.mav.request_data_stream_send(m.target_system, m.target_component,
                                   mavutil.mavlink.MAV_DATA_STREAM_ALL, 10, 1)
    print(f"drone {idx} connected")
    return m

def check_clean_start(m, idx):
    hb = m.recv_match(type='HEARTBEAT', blocking=True, timeout=5)
    armed = hb and (hb.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED)
    pos = latest(m, 'GLOBAL_POSITION_INT')
    alt = pos.relative_alt / 1000.0 if pos else 0
    if armed or alt > 0.5:
        print(f"drone {idx} not on the ground (armed={bool(armed)}, alt={alt:.1f}m)")
        print("restart SITL before running an experiment")
        raise SystemExit
    print(f"drone {idx} confirmed on ground")

def wait_ready(m, idx, timeout=120):
    start = time.time()
    while time.time() - start < timeout:
        msg = m.recv_match(type='SYS_STATUS', blocking=True, timeout=2)
        if msg and msg.onboard_control_sensors_health & PREARM_OK:
            print(f"drone {idx} ready")
            return True
    print(f"drone {idx} not ready after {timeout}s")
    return False

def arm_and_takeoff(m, idx):
    m.set_mode('GUIDED')
    time.sleep(1)

    m.mav.command_long_send(m.target_system, m.target_component,
        mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM, 0, 1, 0, 0, 0, 0, 0, 0)

    deadline = time.time() + 5
    armed_ok = False
    while time.time() < deadline:
        msg = m.recv_match(type=['COMMAND_ACK', 'STATUSTEXT'], blocking=True, timeout=1)
        if msg is None:
            continue
        if msg.get_type() == 'STATUSTEXT':
            print(f"  [{idx}] {msg.text}")
        elif msg.command == mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM:
            armed_ok = msg.result == mavutil.mavlink.MAV_RESULT_ACCEPTED
            print(f"drone {idx} arm {'accepted' if armed_ok else f'REJECTED (result {msg.result})'}")
            break

    if not armed_ok:
        print(f"drone {idx} failed to arm — aborting")
        raise SystemExit

    m.mav.command_long_send(m.target_system, m.target_component,
        mavutil.mavlink.MAV_CMD_NAV_TAKEOFF, 0, 0, 0, 0, 0, 0, 0, ALT)
    print(f"drone {idx} taking off")

# ---- connect and sanity-check ----
drones = [connect(p, i) for i, p in enumerate(PORTS)]
for i, m in enumerate(drones):
    check_clean_start(m, i)
for i, m in enumerate(drones):
    wait_ready(m, i)
for i, m in enumerate(drones):
    arm_and_takeoff(m, i)

# ---- wait for climb, with timeout ----
climb_deadline = time.time() + 60
while True:
    if time.time() > climb_deadline:
        print("timeout — drones did not reach altitude. Restart SITL and retry.")
        raise SystemExit
    alts = [(latest(m, 'GLOBAL_POSITION_INT') or None) for m in drones]
    alts = [(a.relative_alt / 1000.0 if a else 0) for a in alts]
    print(f"climbing: {[round(a,1) for a in alts]}")
    if all(a >= ALT * 0.95 for a in alts):
        break
    time.sleep(1)
print("at altitude — formation starting")

# ---- set leader speed for this experiment ----
for m in drones:
    m.mav.param_set_send(m.target_system, m.target_component,
        b'WPNAV_SPEED', float(SPEED), mavutil.mavlink.MAV_PARAM_TYPE_REAL32)
time.sleep(1)
print(f"leader speed set to {SPEED} cm/s -> logging to {LOGFILE}")

leader = drones[0]
lp = None
while lp is None:
    lp = latest(leader, 'GLOBAL_POSITION_INT')
home_lat, home_lon = lp.lat / 1e7, lp.lon / 1e7

corners = [offset_latlon(home_lat, home_lon, dn, de) for dn, de in
           [(SQUARE, 0), (SQUARE, SQUARE), (0, SQUARE), (0, 0)]]
corner_i = 0

log = open(LOGFILE, 'w', newline='')
w = csv.writer(log)
w.writerow(['t', 'corner', 'heading', 'leader_lat', 'leader_lon',
            'f1_lat', 'f1_lon', 'f1_tgt_lat', 'f1_tgt_lon', 'err_1',
            'f2_lat', 'f2_lon', 'f2_tgt_lat', 'f2_tgt_lon', 'err_2'])

t0 = time.time()
while time.time() - t0 < DURATION:
    lp = latest(leader, 'GLOBAL_POSITION_INT')
    if lp is None:
        time.sleep(1 / LOOP_HZ); continue
    llat, llon = lp.lat / 1e7, lp.lon / 1e7
    heading = lp.hdg / 100.0 if lp.hdg != 65535 else 0.0

    tgt_lat, tgt_lon = corners[corner_i]
    if dist_m(llat, llon, tgt_lat, tgt_lon) < 3.0:
        corner_i = (corner_i + 1) % len(corners)
        tgt_lat, tgt_lon = corners[corner_i]
        print(f"leader -> corner {corner_i}")
    goto(leader, tgt_lat, tgt_lon, ALT)

    row_extra, errs = [], []
    for i in (1, 2):
        dn, de = rotate_offset(heading, *OFFSETS[i])
        dlat, dlon = offset_latlon(llat, llon, dn, de)
        goto(drones[i], dlat, dlon, ALT)
        fp = latest(drones[i], 'GLOBAL_POSITION_INT')
        if fp:
            flat, flon = fp.lat / 1e7, fp.lon / 1e7
            e = round(dist_m(flat, flon, dlat, dlon), 2)
        else:
            flat, flon, e = None, None, None
        row_extra += [flat, flon, dlat, dlon]
        errs.append(e)

    t = round(time.time() - t0, 2)
    w.writerow([t, corner_i, round(heading, 1), llat, llon,
                row_extra[0], row_extra[1], row_extra[2], row_extra[3], errs[0],
                row_extra[4], row_extra[5], row_extra[6], row_extra[7], errs[1]])
    if int(t * LOOP_HZ) % (LOOP_HZ * 2) == 0:
        print(f"t={t:6.1f}  hdg={heading:5.1f}  formation error: {errs}")
    time.sleep(1 / LOOP_HZ)

log.close()
print("landing")
for m in drones:
    m.set_mode('LAND')