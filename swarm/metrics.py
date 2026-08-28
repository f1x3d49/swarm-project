"""Per-agent metrics: order parameter, min inter-agent distance, λ₂.

See CLAUDE.md §5. Each agent computes and logs these from its own world
model (and, for λ₂, its own gossiped view of the neighbor graph — see
swarm/graph.py) — there is no script anywhere that reads all agents' states
to compute a "true" global figure (CLAUDE.md invariant #2). With perfect
comms and full connectivity these local estimates agree with the global
value; once comms degrade (week 5) they will honestly start to diverge,
which is itself part of the resilience story.
"""
import csv
import math
import time

from . import behaviors
from .state import Kind


def order_parameter(self_state, world_model):
    """Vicsek order parameter (Vicsek et al. 1995): magnitude of the mean
    normalized velocity over self + every live peer this agent can see.
    1.0 = perfectly aligned, 0.0 = no coherent heading.
    """
    velocities = [self_state.velocity]
    for entity in world_model.values():
        if entity.kind == Kind.PEER and entity.state.valid:
            velocities.append(entity.state.velocity)

    sum_n = sum_e = 0.0
    counted = 0
    for vn, ve, _vd in velocities:
        speed = math.hypot(vn, ve)
        if speed < 1e-3:  # hovering agents don't have a heading to align to
            continue
        sum_n += vn / speed
        sum_e += ve / speed
        counted += 1

    if counted == 0:
        return 0.0
    return math.hypot(sum_n, sum_e) / counted


def min_neighbor_distance(self_state, world_model):
    """Distance to the closest live peer, or None if this agent sees no one."""
    _entity, dist = behaviors.nearest_peer(world_model, self_state)
    return dist


class MetricsLogger:
    def __init__(self, agent_id, timestamp=None):
        ts = timestamp or time.strftime("%H%M%S")
        self.path = f"metrics_agent{agent_id}_{ts}.csv"
        self._file = open(self.path, "w", newline="")
        self._writer = csv.writer(self._file)
        self._writer.writerow(["t", "phi", "min_neighbor_dist_m", "lambda2", "veto"])
        self._t0 = time.time()

    def log(self, phi, min_dist, lambda2, veto_reason):
        self._writer.writerow([
            round(time.time() - self._t0, 2),
            round(phi, 3),
            round(min_dist, 2) if min_dist is not None else "",
            round(lambda2, 3),
            veto_reason or "",
        ])
        self._file.flush()

    def close(self):
        self._file.close()
