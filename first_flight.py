from pymavlink import mavutil
import time

# Connect to SITL
m = mavutil.mavlink_connection('udp:127.0.0.1:14551')
m.wait_heartbeat()
print("Connected to drone")

# Set Guided mode, arm, take off to 10 m
m.set_mode('GUIDED')
m.arducopter_arm()
m.motors_armed_wait()
print("Armed")
m.mav.command_long_send(m.target_system, m.target_component,
    mavutil.mavlink.MAV_CMD_NAV_TAKEOFF, 0, 0, 0, 0, 0, 0, 0, 10)

time.sleep(15)
print("Landing")
m.set_mode('LAND')