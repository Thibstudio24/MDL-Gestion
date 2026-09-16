#!/usr/bin/env python3
"""Génère les icônes PWA en PNG (pur Python : zlib + struct, aucune dépendance).

Relancer :  python scripts/make_icons.py
"""
from __future__ import annotations

import struct
import zlib
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "static" / "icons"
PRIMARY = (0x33, 0x55, 0x6E)
ACCENT = (0xA7, 0x6A, 0x43)
WHITE = (0xFF, 0xFF, 0xFF)


def rounded(size: float, radius: float, x: float, y: float) -> bool:
    if x < 0 or y < 0 or x >= size or y >= size:
        return False
    cx = min(max(x, radius), size - radius)
    cy = min(max(y, radius), size - radius)
    return (x - cx) ** 2 + (y - cy) ** 2 <= radius ** 2


def in_rect(x, y, x0, y0, x1, y1) -> bool:
    return x0 <= x <= x1 and y0 <= y <= y1


def in_circle(x, y, cx, cy, r) -> bool:
    return (x - cx) ** 2 + (y - cy) ** 2 <= r * r


def draw(size: int, maskable: bool = False, badge: bool = False) -> bytes:
    scale = size / 512
    pad = 96 * scale if maskable else 0  # zone de sécurité pour les icônes maskable
    canvas = size
    pixels = bytearray()
    house_top = 168 * scale + pad * 0.35
    roof_apex = 118 * scale + pad * 0.35
    body_left = 148 * scale
    body_right = 364 * scale
    body_bottom = 348 * scale
    ground_top = 372 * scale
    ground_bottom = 392 * scale
    door_left = 208 * scale
    door_right = 268 * scale
    door_top = 268 * scale
    win_left = 296 * scale
    win_right = 336 * scale
    win_top = 258 * scale
    win_bottom = 306 * scale
    for y in range(canvas):
        row = bytearray(b"\x00")  # filtre « none »
        for x in range(canvas):
            color = (0, 0, 0, 0)
            if badge:
                centre = canvas / 2
                rayon = canvas / 2 - max(1.0, 3 * scale)
                if in_circle(x + 0.5, y + 0.5, centre, centre, rayon):
                    color = (0xA6, 0x3A, 0x3A, 255)
                    if in_circle(x + 0.5, y + 0.5, centre, centre, rayon * 0.42):
                        color = WHITE + (255,)
            elif rounded(canvas, 112 * scale, x + 0.5, y + 0.5):
                color = PRIMARY + (255,)
                # toit (triangle)
                if roof_apex <= y <= house_top:
                    half = (y - roof_apex) / max(1.0, house_top - roof_apex) * (canvas / 2 - 96 * scale)
                    if abs(x + 0.5 - canvas / 2) <= half:
                        color = WHITE + (255,)
                elif in_rect(x, y, body_left, house_top, body_right, body_bottom):
                    color = WHITE + (255,)
                elif in_rect(x, y, door_left, door_top, door_right, body_bottom):
                    color = ACCENT + (255,)
                elif in_rect(x, y, win_left, win_top, win_right, win_bottom):
                    color = PRIMARY + (255,)
                elif in_rect(x, y, 108 * scale, ground_top, canvas - 108 * scale, ground_bottom):
                    color = WHITE + (255,)
            row += bytes(color)
        pixels += row
    return zlib.compress(bytes(pixels), 9)


def write_png(path: Path, size: int, maskable: bool = False, badge: bool = False) -> None:
    raw = draw(size, maskable=maskable, badge=badge)
    header = b"\x89PNG\r\n\x1a\n"

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (struct.pack(">I", len(data)) + tag + data
                + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))

    ihdr = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)
    path.write_bytes(header + chunk(b"IHDR", ihdr) + chunk(b"IDAT", raw) + chunk(b"IEND", b""))
    print("%s (%d octets)" % (path.name, path.stat().st_size))


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    write_png(OUT / "app-192.png", 192)
    write_png(OUT / "app-512.png", 512)
    write_png(OUT / "maskable-512.png", 512, maskable=True)
    write_png(OUT / "badge-72.png", 72, badge=True)
    (OUT / "favicon.svg").write_text(
        (Path(__file__).resolve().parent.parent / "static" / "img" / "mark.svg").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    print("favicon.svg copié")


if __name__ == "__main__":
    main()
