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
COTTON = (0xFD, 0xFC, 0xF8)
SEED = (0x25, 0x63, 0xEB)

# The boll is a cluster of overlapping puffs, and the seeds sit inside it.
PUFFS = [
    (32.0, 19.0, 9.0),
    (21.0, 26.0, 8.5),
    (43.0, 27.0, 8.0),
    (32.0, 33.0, 10.0),
    (19.0, 38.0, 7.5),
    (45.0, 39.0, 7.5),
]
SEEDS = [
    (28.0, 30.0, 2.4),
    (36.0, 31.0, 2.2),
    (32.0, 39.0, 2.4),
]

SAMPLES = 4  # supersampling factor per axis

# GitHub Pages serves the docs/ directory as the site root, so the site
# assets live under docs/assets, not at the repository root.
SITE_ROOT = Path(__file__).resolve().parent.parent / "docs"
OUTPUT_DIR = SITE_ROOT / "assets" / "images"


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


def inside_circle(x: float, y: float, centre: tuple[float, float], radius: float) -> bool:
    cx, cy = centre
    return math.hypot(x - cx, y - cy) <= radius


def sample_colour(x: float, y: float):
    """Premultiplied RGBA for one sample."""
    if not inside_rounded_rect(x, y):
        return (0.0, 0.0, 0.0, 0.0)
    colour = BACKDROP
    if any(inside_circle(x, y, (cx, cy), r) for cx, cy, r in PUFFS):
        colour = COTTON
        if any(inside_circle(x, y, (cx, cy), r) for cx, cy, r in SEEDS):
            colour = SEED
    return (colour[0], colour[1], colour[2], 255.0)


def render(pixels: int) -> list[bytes]:
    """Render the icon at the given pixel size and return one RGBA row per line."""
    scale = SIZE / pixels

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
                    sample = sample_colour(x, y)
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

    # Browsers also probe /favicon.ico at the site root without asking the page.
    (SITE_ROOT / "favicon.ico").write_bytes(ico)
    print("wrote ../favicon.ico")


if __name__ == "__main__":
    main()
