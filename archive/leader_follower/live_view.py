import sys, csv, math
import matplotlib.pyplot as plt
import matplotlib.animation as animation

if len(sys.argv) < 2:
    print("usage: python3 live_view.py <formation_csv_file>")
    sys.exit(1)

f = open(sys.argv[1], newline='')
reader = csv.DictReader(f)
home = None
leader_xy, f1_xy, f2_xy = [], [], []
f1_tgt_xy, f2_tgt_xy = [], []

fig, ax = plt.subplots(figsize=(6, 6))
ax.set_aspect('equal')
ax.set_xlabel('east (m)'); ax.set_ylabel('north (m)')
ax.set_title('Formation — live top-down view')

leader_l, = ax.plot([], [], 'o-', color='tab:blue', ms=4, label='leader')
f1_l, = ax.plot([], [], 'o-', color='tab:orange', ms=4, label='follower 1')
f2_l, = ax.plot([], [], 'o-', color='tab:green', ms=4, label='follower 2')
f1_tgt_l, = ax.plot([], [], '--', color='tab:orange', alpha=0.4, lw=1, label='f1 target path')
f2_tgt_l, = ax.plot([], [], '--', color='tab:green', alpha=0.4, lw=1, label='f2 target path')
ax.legend(loc='upper right', fontsize=8)

def to_local(lat, lon):
    dn = (lat - home[0]) * 111320.0
    de = (lon - home[1]) * 111320.0 * math.cos(math.radians(home[0]))
    return de, dn

def update(_):
    global home
    for row in reader:
        try:
            llat, llon = float(row['leader_lat']), float(row['leader_lon'])
        except ValueError:
            continue
        if home is None:
            home = (llat, llon)
        leader_xy.append(to_local(llat, llon))

        if row['f1_tgt_lat']:
            f1_tgt_xy.append(to_local(float(row['f1_tgt_lat']), float(row['f1_tgt_lon'])))
        if row['f1_lat']:
            f1_xy.append(to_local(float(row['f1_lat']), float(row['f1_lon'])))

        if row['f2_tgt_lat']:
            f2_tgt_xy.append(to_local(float(row['f2_tgt_lat']), float(row['f2_tgt_lon'])))
        if row['f2_lat']:
            f2_xy.append(to_local(float(row['f2_lat']), float(row['f2_lon'])))

    if leader_xy: leader_l.set_data(*zip(*leader_xy))
    if f1_xy: f1_l.set_data(*zip(*f1_xy))
    if f2_xy: f2_l.set_data(*zip(*f2_xy))
    if f1_tgt_xy: f1_tgt_l.set_data(*zip(*f1_tgt_xy))
    if f2_tgt_xy: f2_tgt_l.set_data(*zip(*f2_tgt_xy))
    ax.relim(); ax.autoscale_view()
    return leader_l, f1_l, f2_l, f1_tgt_l, f2_tgt_l

ani = animation.FuncAnimation(fig, update, interval=500, cache_frame_data=False)
plt.show()