#!/usr/bin/env python3
"""Rasterize the cotton seed favicon into the PNG and ICO sizes a browser wants.

The vector source of truth is assets/images/favicon.svg. This script mirrors
those shapes, so if you change the SVG, change the constants here too.

    python3 scripts/make-favicon.py

It needs nothing but the standard library, which keeps the icon reproducible
from a clean checkout.
"""

from __future__ import annotations

import math
import struct
import zlib
from pathlib import Path

# Canvas is 64x64 in the SVG, everything below is in those units.
SIZE = 64.0
CORNER_RADIUS = 14.0

BACKDROP = (0x25, 0x63, 0xEB)
SEED = (0xFD, 0xFC, 0xF8)
SEAM = (0xDB, 0xE4, 0xF4)

# The seed is the convex hull of a circle and the tip above it.
SEED_CENTRE = (32.0, 37.0)
SEED_RADIUS = 18.0
SEED_TIP = (32.0, 9.0)

# The seam is the cubic bezier from the SVG path.
SEAM_START = (31.0, 14.5)
SEAM_CONTROL_1 = (29.5, 25.0)
SEAM_CONTROL_2 = (29.0, 35.0)
SEAM_END = (30.0, 50.0)
SEAM_WIDTH = 2.6

SAMPLES = 4  # supersampling factor per axis

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "assets" / "images"


def tangent_points() -> tuple[tuple[float, float], tuple[float, float]]:
    """Where the lines from the tip touch the circle."""
    cx, cy = SEED_CENTRE
    tx, ty = SEED_TIP
    dx, dy = tx - cx, ty - cy
    distance = math.hypot(dx, dy)
    alpha = math.acos(SEED_RADIUS / distance)
    # Unit vector from the centre to the tip, rotated by +/- alpha.
    ux, uy = dx / distance, dy / distance
    points = []
    for sign in (1.0, -1.0):
        rx = ux * math.cos(alpha) - uy * math.sin(alpha) * sign
        ry = ux * math.sin(alpha) * sign + uy * math.cos(alpha)
        points.append((cx + SEED_RADIUS * rx, cy + SEED_RADIUS * ry))
    return points[0], points[1]


def inside_rounded_rect(x: float, y: float) -> bool:
    """Rounded square covering the whole canvas."""
    half = SIZE / 2.0
    dx = abs(x - half) - (half - CORNER_RADIUS)
    dy = abs(y - half) - (half - CORNER_RADIUS)
    if dx <= 0.0 and dy <= 0.0:
        return True
    dx = max(dx, 0.0)
    dy = max(dy, 0.0)
    return math.hypot(dx, dy) <= CORNER_RADIUS


def inside_circle(x: float, y: float) -> bool:
    cx, cy = SEED_CENTRE
    return math.hypot(x - cx, y - cy) <= SEED_RADIUS


def inside_triangle(x: float, y: float, points) -> bool:
    (x1, y1), (x2, y2), (x3, y3) = points

    def sign(ax, ay, bx, by, cx, cy):
        return (ax - cx) * (by - cy) - (bx - cx) * (ay - cy)

    d1 = sign(x, y, x1, y1, x2, y2)
    d2 = sign(x, y, x2, y2, x3, y3)
    d3 = sign(x, y, x3, y3, x1, y1)
    has_negative = d1 < 0 or d2 < 0 or d3 < 0
    has_positive = d1 > 0 or d2 > 0 or d3 > 0
    return not (has_negative and has_positive)


def bezier_points(start, control_1, control_2, end, steps: int = 64):
    points = []
    for index in range(steps + 1):
        t = index / steps
        inverse = 1.0 - t
        x = (
            inverse ** 3 * start[0]
            + 3 * inverse ** 2 * t * control_1[0]
            + 3 * inverse * t ** 2 * control_2[0]
            + t ** 3 * end[0]
        )
        y = (
            inverse ** 3 * start[1]
            + 3 * inverse ** 2 * t * control_1[1]
            + 3 * inverse * t ** 2 * control_2[1]
            + t ** 3 * end[1]
        )
        points.append((x, y))
    return points


def distance_to_polyline(x: float, y: float, points) -> float:
    best = float("inf")
    for (x1, y1), (x2, y2) in zip(points, points[1:]):
        dx, dy = x2 - x1, y2 - y1
        length_squared = dx * dx + dy * dy
        if length_squared == 0.0:
            candidate = math.hypot(x - x1, y - y1)
        else:
            t = max(0.0, min(1.0, ((x - x1) * dx + (y - y1) * dy) / length_squared))
            candidate = math.hypot(x - (x1 + t * dx), y - (y1 + t * dy))
        best = min(best, candidate)
    return best


def sample_colour(x: float, y: float, seed_points, seam_points):
    """Premultiplied RGBA for one sample."""
    if not inside_rounded_rect(x, y):
        return (0.0, 0.0, 0.0, 0.0)
    colour = BACKDROP
    if inside_circle(x, y) or inside_triangle(x, y, seed_points):
        colour = SEED
        if distance_to_polyline(x, y, seam_points) <= SEAM_WIDTH / 2.0:
            colour = SEAM
    return (colour[0], colour[1], colour[2], 255.0)


def render(pixels: int) -> list[bytes]:
    """Render the icon at the given pixel size and return one RGBA row per line."""
    scale = SIZE / pixels
    seed_points = (SEED_TIP, *tangent_points())
    seam_points = bezier_points(SEAM_START, SEAM_CONTROL_1, SEAM_CONTROL_2, SEAM_END)

    rows = []
    offsets = [(index + 0.5) / SAMPLES for index in range(SAMPLES)]
    total = SAMPLES * SAMPLES
    for row in range(pixels):
        line = bytearray()
        for column in range(pixels):
            red = green = blue = alpha = 0.0
            for offset_y in offsets:
                for offset_x in offsets:
                    x = (column + offset_x) * scale
                    y = (row + offset_y) * scale
                    sample = sample_colour(x, y, seed_points, seam_points)
                    red += sample[0] * sample[3]
                    green += sample[1] * sample[3]
                    blue += sample[2] * sample[3]
                    alpha += sample[3]
            if alpha > 0.0:
                red /= alpha
                green /= alpha
                blue /= alpha
                alpha /= total
            line += bytes(
                (
                    int(round(red)),
                    int(round(green)),
                    int(round(blue)),
                    int(round(alpha)),
                )
            )
        rows.append(bytes(line))
    return rows


def encode_png(pixels: int, rows: list[bytes]) -> bytes:
    def chunk(tag: bytes, payload: bytes) -> bytes:
        return (
            struct.pack(">I", len(payload))
            + tag
            + payload
            + struct.pack(">I", zlib.crc32(tag + payload) & 0xFFFFFFFF)
        )

    header = struct.pack(">IIBBBBB", pixels, pixels, 8, 6, 0, 0, 0)
    # Every scanline is prefixed with its filter type, 0 meaning "no filter".
    raw = b"".join(b"\x00" + row for row in rows)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(raw, 9))
        + chunk(b"IEND", b"")
    )


def encode_ico(images: list[tuple[int, bytes]]) -> bytes:
    """Pack PNG encoded images into an ICO container."""
    count = len(images)
    header = struct.pack("<HHH", 0, 1, count)
    offset = 6 + 16 * count
    entries = b""
    payloads = b""
    for size, payload in images:
        entries += struct.pack(
            "<BBBBHHII",
            0 if size >= 256 else size,
            0 if size >= 256 else size,
            0,
            0,
            1,
            32,
            len(payload),
            offset,
        )
        payloads += payload
        offset += len(payload)
    return header + entries + payloads


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    sizes = (16, 32, 48, 180, 192, 512)
    pngs: dict[int, bytes] = {}
    for size in sizes:
        png = encode_png(size, render(size))
        pngs[size] = png
        name = f"favicon-{size}.png"
        (OUTPUT_DIR / name).write_bytes(png)
        print(f"wrote {name} ({len(png)} bytes)")

    ico = encode_ico([(size, pngs[size]) for size in (16, 32, 48)])
    (OUTPUT_DIR / "favicon.ico").write_bytes(ico)
    print(f"wrote favicon.ico ({len(ico)} bytes)")


if __name__ == "__main__":
    main()
