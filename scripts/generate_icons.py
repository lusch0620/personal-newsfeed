#!/usr/bin/env python3
"""Generate PWA icons for the personal newsfeed. stdlib only — no Pillow needed."""
import struct, zlib
from pathlib import Path

DOCS = Path(__file__).parent.parent / "docs"
OUT  = DOCS / "icons"

BG   = (7, 8, 12)       # --bg: #07080c
ACC  = (52, 211, 153)   # --aw: #34d399 (site accent green)


def png_bytes(size: int, pixels: list) -> bytes:
    def chunk(name: bytes, data: bytes) -> bytes:
        c = name + data
        return struct.pack('>I', len(data)) + c + struct.pack('>I', zlib.crc32(c) & 0xffffffff)
    raw = b''.join(
        b'\x00' + b''.join(bytes(px) for px in row)
        for row in pixels
    )
    return (
        b'\x89PNG\r\n\x1a\n'
        + chunk(b'IHDR', struct.pack('>IIBBBBB', size, size, 8, 2, 0, 0, 0))
        + chunk(b'IDAT', zlib.compress(raw, 9))
        + chunk(b'IEND', b'')
    )


def make_pixels(size: int) -> list:
    """Dark bg with 'N' letter in accent green."""
    sw  = max(2, int(size * 0.10))  # stroke width
    lx  = int(size * 0.27)          # left stem x-start
    rx  = int(size * 0.63)          # right stem x-start
    ty  = int(size * 0.22)          # letter top y
    by  = int(size * 0.78)          # letter bottom y
    dx0, dy0 = lx + sw // 2, ty    # diagonal start (center of left stem top)
    dx1, dy1 = rx + sw // 2, by    # diagonal end   (center of right stem bottom)

    pixels = []
    for y in range(size):
        row = []
        for x in range(size):
            in_left  = (lx <= x < lx + sw) and (ty <= y <= by)
            in_right = (rx <= x < rx + sw) and (ty <= y <= by)
            in_diag  = False
            if dx1 != dx0:
                t = (x - dx0) / (dx1 - dx0)
                if 0.0 <= t <= 1.0:
                    diag_y = dy0 + t * (dy1 - dy0)
                    if abs(y - diag_y) <= sw * 0.65:
                        in_diag = True
            row.append(ACC if (in_left or in_right or in_diag) else BG)
        pixels.append(row)
    return pixels


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for size in (192, 512):
        data = png_bytes(size, make_pixels(size))
        path = OUT / f"icon-{size}.png"
        path.write_bytes(data)
        print(f"Wrote {path}  ({len(data):,} bytes)")


if __name__ == '__main__':
    main()
