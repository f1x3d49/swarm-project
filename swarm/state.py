"""StateEstimate and TrackedEntity — see docs/ARCHITECTURE.md Section 0.

No component ever passes a bare position. Every estimate carries covariance
(or the minimal sigma_h/sigma_v), a measurement timestamp, a source, and a
validity flag.
"""
from dataclasses import dataclass
from enum import Enum
import time


class Source(Enum):
    GPS = "GPS"
    FLOW = "FLOW"
    UWB = "UWB"
    VISION = "VISION"
    DEAD_RECKON = "DEAD_RECKON"
    GROUND_TRUTH = "GROUND_TRUTH"


class Kind(Enum):
    PEER = "PEER"
    OBSTACLE = "OBSTACLE"
    UNKNOWN = "UNKNOWN"
    AIRCRAFT = "AIRCRAFT"


class DetectedBy(Enum):
    RADIO = "RADIO"
    PROXIMITY = "PROXIMITY"
    VISION = "VISION"


@dataclass
class StateEstimate:
    position: tuple          # (north, east, down), meters, local NED
    velocity: tuple          # (vn, ve, vd), m/s
    sigma_horizontal: float  # meters
    sigma_vertical: float    # meters
    timestamp: float         # time.time() when measured, not when received
    source: Source
    valid: bool = True

    def to_dict(self):
        return {
            "position": list(self.position),
            "velocity": list(self.velocity),
            "sigma_horizontal": self.sigma_horizontal,
            "sigma_vertical": self.sigma_vertical,
            "timestamp": self.timestamp,
            "source": self.source.value,
            "valid": self.valid,
        }

    @classmethod
    def from_dict(cls, d):
        return cls(
            position=tuple(d["position"]),
            velocity=tuple(d["velocity"]),
            sigma_horizontal=d["sigma_horizontal"],
            sigma_vertical=d["sigma_vertical"],
            timestamp=d["timestamp"],
            source=Source(d["source"]),
            valid=d["valid"],
        )


@dataclass
class TrackedEntity:
    entity_id: str
    kind: Kind
    state: StateEstimate
    last_seen: float          # time.time() this entity was last updated
    detected_by: DetectedBy
    class_label: str = None
    confidence: float = 1.0

    def age(self, now=None):
        return (now if now is not None else time.time()) - self.last_seen
