"""Render the Depoloma icon to PNG and ICO using only the standard library.

    python tools/make_icon.py

Writes depoloma/web/icon.png (256 px) and depoloma/web/icon.ico (16–256 px).
The drawing mirrors depoloma/web/icon.svg: a teal→blue rounded square with a
white "disk usage" ring.
"""
import math
import os
import struct
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "depoloma", "web")
STOPS = ((0.0, (0x19, 0xD3, 0xC0)), (0.5, (0x0D, 0x9F, 0xB0)), (1.0, (0x2A, 0x78, 0xD6)))


def gradient(t):
    t = min(1.0, max(0.0, t))
    for (t0, c0), (t1, c1) in zip(STOPS, STOPS[1:]):
        if t <= t1:
            k = (t - t0) / (t1 - t0)
            return tuple(c0[i] + (c1[i] - c0[i]) * k for i in range(3))
    return STOPS[-1][1]


def sample(x, y):
    """Colour (r, g, b, a) of the icon at (x, y) in a 64×64 design space."""
    # rounded square, radius 15
    dx = max(15 - x, 0, x - 49)
    dy = max(15 - y, 0, y - 49)
    if dx * dx + dy * dy > 15 * 15:
        return 0.0, 0.0, 0.0, 0.0
    r, g, b = gradient((x + y) / 128.0)
    white = 0.0
    d = math.hypot(x - 32, y - 32)
    if d <= 4:                                        # hub
        white = 1.0
    elif 13 <= d <= 21:                               # ring: full track, 82 % "used" arc
        ang = (math.degrees(math.atan2(x - 32, 32 - y)) + 360) % 360      # 0° = top, clockwise
        white = 1.0 if ang <= 300 else 0.32
    else:
        # round caps of the used arc
        for cap_deg in (0, 300):
            cx = 32 + 17 * math.sin(math.radians(cap_deg))
            cy = 32 - 17 * math.cos(math.radians(cap_deg))
            if math.hypot(x - cx, y - cy) <= 4:
                white = 1.0
    return r + (255 - r) * white, g + (255 - g) * white, b + (255 - b) * white, 255.0


def render(size, ss=4):
    rows = []
    scale = 64.0 / size
    n = ss * ss
    for py in range(size):
        row = bytearray()
        for px in range(size):
            acc = [0.0, 0.0, 0.0, 0.0]
            for sy in range(ss):
                for sx in range(ss):
                    r, g, b, a = sample((px + (sx + 0.5) / ss) * scale, (py + (sy + 0.5) / ss) * scale)
                    acc[0] += r * a
                    acc[1] += g * a
                    acc[2] += b * a
                    acc[3] += a
            if acc[3]:
                row += bytes((int(acc[0] / acc[3] + 0.5), int(acc[1] / acc[3] + 0.5), int(acc[2] / acc[3] + 0.5),
                              int(acc[3] / n + 0.5)))
            else:
                row += b"\0\0\0\0"
        rows.append(bytes(row))
    return rows


def png(rows, size):
    def chunk(kind, data):
        body = kind + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)
    raw = b"".join(b"\0" + row for row in rows)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


def main():
    images = {}
    for size in (16, 24, 32, 48, 64, 128, 256):
        images[size] = png(render(size), size)
    with open(os.path.join(OUT, "icon.png"), "wb") as fh:
        fh.write(images[256])
    header = struct.pack("<HHH", 0, 1, len(images))
    offset = 6 + 16 * len(images)
    entries = b""
    for size, data in images.items():
        entries += struct.pack("<BBBBHHII", size % 256, size % 256, 0, 0, 1, 32, len(data), offset)
        offset += len(data)
    with open(os.path.join(OUT, "icon.ico"), "wb") as fh:
        fh.write(header + entries + b"".join(images.values()))
    print("wrote icon.png and icon.ico")


if __name__ == "__main__":
    main()
