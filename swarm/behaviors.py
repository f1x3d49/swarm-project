"""Reynolds behaviors — see docs/ARCHITECTURE.md §5.

Each behavior is a pure function `(world_model, self_state) -> (velocity,
weight)`, exactly per ARCHITECTURE.md's behavior interface. They read the
world model and self state and return a desired NED velocity direction plus
how strongly they want it. They never talk to MAVLink and never know about
each other or about the arbiter that blends them.

Week 2 scope: flocking is horizontal only — every returned velocity has
vd=0, altitude hold is left to GUIDED mode sending zero vertical velocity.
"""
import math

from . import config
from .state import Kind

VELOCITY_ZERO = (0.0, 0.0, 0.0)


def _horizontal_delta(from_state, to_state):
    dn = to_state.position[0] - from_state.position[0]
    de = to_state.position[1] - from_state.position[1]
    return dn, de


def _peers_within(world_model, self_state, radius):
    """[(entity, dist, dn, de), ...] for live PEER entities within radius."""
    out = []
    for entity in world_model.values():
        if entity.kind != Kind.PEER or not entity.state.valid:
            continue
        dn, de = _horizontal_delta(self_state, entity.state)
        dist = math.hypot(dn, de)
        if dist <= radius:
            out.append((entity, dist, dn, de))
    return out


def nearest_peer(world_model, self_state):
    """(entity, dist) for the closest live PEER, or (None, None)."""
    best, best_dist = None, None
    for entity in world_model.values():
        if entity.kind != Kind.PEER or not entity.state.valid:
            continue
        dn, de = _horizontal_delta(self_state, entity.state)
        dist = math.hypot(dn, de)
        if best_dist is None or dist < best_dist:
            best, best_dist = entity, dist
    return best, best_dist


def separation(world_model, self_state):
    """Steer away from neighbors inside SEPARATION_RADIUS_M, harder when closer."""
    neighbors = _peers_within(world_model, self_state, config.SEPARATION_RADIUS_M)
    if not neighbors:
        return VELOCITY_ZERO, 0.0

    vn = ve = 0.0
    for _entity, dist, dn, de in neighbors:
        dist = max(dist, 0.1)  # avoid blow-up as neighbors approach 0m
        strength = 1.0 / dist
        vn -= (dn / dist) * strength
        ve -= (de / dist) * strength
    return (vn, ve, 0.0), config.W_SEPARATION


def alignment(world_model, self_state):
    """Steer toward the average heading of neighbors within NEIGHBOR_RADIUS_M."""
    neighbors = _peers_within(world_model, self_state, config.NEIGHBOR_RADIUS_M)
    if not neighbors:
        return VELOCITY_ZERO, 0.0

    n = len(neighbors)
    vn = sum(entity.state.velocity[0] for entity, _, _, _ in neighbors) / n
    ve = sum(entity.state.velocity[1] for entity, _, _, _ in neighbors) / n
    return (vn, ve, 0.0), config.W_ALIGNMENT


def cohesion(world_model, self_state):
    """Steer toward the average position of neighbors within NEIGHBOR_RADIUS_M."""
    neighbors = _peers_within(world_model, self_state, config.NEIGHBOR_RADIUS_M)
    if not neighbors:
        return VELOCITY_ZERO, 0.0

    n = len(neighbors)
    dn = sum(dn for _, _, dn, _ in neighbors) / n
    de = sum(de for _, _, _, de in neighbors) / n
    return (dn, de, 0.0), config.W_COHESION


def group_objective(world_model, self_state):
    """Steer toward the scripted waypoint. Stands in for operator control
    until week 4; ignores world_model like every other behavior signature.
    """
    tn, te, _td = config.GROUP_OBJECTIVE_TARGET_NED
    dn = tn - self_state.position[0]
    de = te - self_state.position[1]
    dist = math.hypot(dn, de)
    if dist < 1e-6:
        return VELOCITY_ZERO, config.W_GROUP_OBJECTIVE
    return (dn / dist, de / dist, 0.0), config.W_GROUP_OBJECTIVE


BEHAVIORS = [separation, alignment, cohesion, group_objective]
