"""Lat/lon <-> local NED conversion, equirectangular approximation.

Same approximation formation.py already used for its dist_m/offset_latlon
helpers; kept accurate enough over swarm-scale distances (tens of meters).
"""
import math


def latlon_to_ned(origin_lat, origin_lon, lat, lon, alt):
    dn = (lat - origin_lat) * 111320.0
    de = (lon - origin_lon) * 111320.0 * math.cos(math.radians(origin_lat))
    dd = -alt  # NED: down is negative of altitude-above-origin
    return dn, de, dd
