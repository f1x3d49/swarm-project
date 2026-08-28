"""Blend weighted behaviors, saturate, apply the safety veto.

See docs/ARCHITECTURE.md §5 ("ARBITER and the safety veto"). This is the
only place a velocity command gets finalized. Behaviors never see MAVLink;
the veto here overrides every behavior's vote and can never be outvoted.

Week 2 scope: geofence and minimum-separation floor only (per the roadmap).
Battery floor, comms-loss failsafe, and altitude limits are explicitly not
built yet — they need inputs (battery telemetry, comms staleness policy,
hard altitude bounds) that don't exist until later weeks.
"""
import math

from . import behaviors, config


def blend(behavior_outputs):
    """Weighted average of (velocity, weight) pairs. Zero-weight votes (a
    behavior that found nothing to react to) drop out entirely.
    """
    total_weight = sum(w for _v, w in behavior_outputs)
    if total_weight <= 0:
        return (0.0, 0.0, 0.0)

    vn = sum(v[0] * w for v, w in behavior_outputs) / total_weight
    ve = sum(v[1] * w for v, w in behavior_outputs) / total_weight
    vd = sum(v[2] * w for v, w in behavior_outputs) / total_weight
    return (vn, ve, vd)


def saturate(velocity, max_speed):
    vn, ve, vd = velocity
    speed = math.hypot(vn, ve)
    if speed > max_speed:
        scale = max_speed / speed
        vn, ve = vn * scale, ve * scale
    return (vn, ve, vd)


def safety_veto(velocity, world_model, self_state):
    """Returns (velocity, reason). reason is None if nothing fired."""
    entity, dist = behaviors.nearest_peer(world_model, self_state)
    if entity is not None and dist < config.MIN_SEPARATION_M:
        # vector from the offending neighbor toward self — i.e. away from it
        dn = self_state.position[0] - entity.state.position[0]
        de = self_state.position[1] - entity.state.position[1]
        d = max(math.hypot(dn, de), 0.1)
        vn = (dn / d) * config.MAX_SPEED_MPS
        ve = (de / d) * config.MAX_SPEED_MPS
        return (vn, ve, 0.0), "MIN_SEPARATION"

    origin_dist = math.hypot(self_state.position[0], self_state.position[1])
    if origin_dist > config.GEOFENCE_RADIUS_M:
        vn = -self_state.position[0] / origin_dist * config.MAX_SPEED_MPS
        ve = -self_state.position[1] / origin_dist * config.MAX_SPEED_MPS
        return (vn, ve, 0.0), "GEOFENCE"

    return velocity, None


def arbitrate(world_model, self_state):
    """Run every behavior, blend, saturate, veto. Returns (velocity, veto_reason)."""
    outputs = [b(world_model, self_state) for b in behaviors.BEHAVIORS]
    velocity = blend(outputs)
    velocity = saturate(velocity, config.MAX_SPEED_MPS)
    velocity, veto_reason = safety_veto(velocity, world_model, self_state)
    return velocity, veto_reason
