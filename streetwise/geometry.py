"""Voting-district boundaries, read straight from the shapefile the IEC's
boundaries come as, so the project needs no GIS library to check that a
panorama is inside its district."""

import math
import struct
from pathlib import Path

METRES_PER_DEGREE = 111_320


def read_boundaries(shp_path, wanted):
    """{district number: [ring, ...]} for the districts in `wanted`, each ring
    a list of (longitude, latitude). Reads the .shp and the .dbf beside it;
    the .dbf must have a VDNumber column."""
    shp_path = Path(shp_path)
    numbers = _vd_numbers(shp_path.with_suffix(".dbf"))
    boundaries = {}
    with open(shp_path, "rb") as shp:
        shp.seek(100)
        for number in numbers:
            _, length = struct.unpack(">2i", shp.read(8))
            content = shp.read(length * 2)
            if number not in wanted:
                continue
            shape_type, = struct.unpack("<i", content[:4])
            if shape_type != 5:  # Polygon
                continue
            parts, points = struct.unpack("<2i", content[36:44])
            starts = struct.unpack(f"<{parts}i", content[44:44 + 4 * parts])
            xy = struct.unpack(f"<{2 * points}d", content[44 + 4 * parts:44 + 4 * parts + 16 * points])
            coords = list(zip(xy[0::2], xy[1::2]))
            ends = list(starts[1:]) + [points]
            boundaries[number] = [coords[a:b] for a, b in zip(starts, ends)]
    return boundaries


def _vd_numbers(dbf_path):
    """The VDNumber of each record, in file order."""
    with open(dbf_path, "rb") as dbf:
        count, header, size = struct.unpack("<xxxxIHH", dbf.read(12))
        dbf.seek(32)
        fields, offset = {}, 1  # each record starts with a deletion flag
        while (descriptor := dbf.read(32))[0] != 0x0D:
            name = descriptor[:11].split(b"\0")[0].decode()
            fields[name] = (offset, descriptor[16])
            offset += descriptor[16]
        start, width = fields["VDNumber"]
        dbf.seek(header)
        numbers = []
        for _ in range(count):
            record = dbf.read(size)
            numbers.append(record[start:start + width].decode().strip().split(".")[0])
        return numbers


def contains(rings, lng, lat):
    """Even-odd rule over every ring, so holes count as outside."""
    inside = False
    for ring in rings:
        for (x1, y1), (x2, y2) in zip(ring, ring[1:] + ring[:1]):
            if (y1 > lat) != (y2 > lat) and lng < x1 + (lat - y1) * (x2 - x1) / (y2 - y1):
                inside = not inside
    return inside


def distance_to_edge(rings, lng, lat):
    """Metres from the point to the nearest stretch of boundary."""
    scale = math.cos(math.radians(lat))
    best = math.inf
    for ring in rings:
        for (x1, y1), (x2, y2) in zip(ring, ring[1:] + ring[:1]):
            ax, ay = (x1 - lng) * scale, y1 - lat
            bx, by = (x2 - lng) * scale, y2 - lat
            dx, dy = bx - ax, by - ay
            t = 0 if dx == dy == 0 else max(0, min(1, -(ax * dx + ay * dy) / (dx * dx + dy * dy)))
            best = min(best, math.hypot(ax + t * dx, ay + t * dy))
    return best * METRES_PER_DEGREE


def bounds(rings):
    xs = [x for ring in rings for x, _ in ring]
    ys = [y for ring in rings for _, y in ring]
    return min(xs), min(ys), max(xs), max(ys)
