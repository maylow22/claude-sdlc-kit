#!/usr/bin/env python3
"""Builds the Claudemon app icon - the artwork Safari picks up when the dashboard is
added to the macOS Dock.

Two steps, because there is no SVG rasterizer to depend on:

    tools/make_icon.py svg                 # writes assets/icon.svg (the source of truth)
    <render icon.svg to a 1024x1024 PNG>   # any browser will do
    tools/make_icon.py png shot.png        # writes assets/icon-*.png

The second step is what the SVG cannot do itself: it cuts the artwork to the Apple
squircle, lays the top rim light along that same curve, and box-filters the master down
to the sizes the page asks for. The corners come out transparent, so the icon looks right
whether or not the system applies its own mask on top.
"""
from __future__ import annotations

import argparse
import math
import pathlib
import struct
import sys
import zlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"
SIZES = (1024, 512, 180, 32)

S = 1024          # master canvas
CX, CY = 512, 436  # the mark sits high; the trace below carries the lower half
RAYS = 11          # odd, so the burst is symmetric about the vertical and never square
R_TIP = 292.0      # where a ray ends, round cap included
R_IN = 40.0        # where it starts - inside this the eleven rays fuse into the core
RAYW = 40.0        # ray thickness, constant: blunt rays, not a twinkling star
HUB = 44.0

# eleven rays leave a gap pointing straight down, and the beat rises into it:
# the trace and the mark read as one object rather than a logo with a rule under it
TRACE = "M 240 802 H 440 L 466 822 L 508 672 L 540 868 L 568 802 H 784"
TRACE_W = 24

N = 5.0           # superellipse exponent - the usual stand-in for Apple's squircle
RIM_FROM = 0.984  # where the top rim light starts, as a fraction of the squircle radius
RIM_ALPHA = 0.14


# ---------------------------------------------------------------- svg

def ray(k: int) -> str:
    """One ray as a single stroked segment. The round cap is what gives the burst its
    blunt Claude-ish rays, so the drawn segment stops half a stroke short of the tip."""
    a = math.radians(90.0 + k * 360.0 / RAYS)
    dx, dy = math.cos(a), -math.sin(a)      # SVG y grows downwards
    inner, outer = R_IN, R_TIP - RAYW / 2
    return (f"M {CX + inner * dx:.1f} {CY + inner * dy:.1f} "
            f"L {CX + outer * dx:.1f} {CY + outer * dy:.1f}")


def build_svg() -> str:
    burst = " ".join(ray(k) for k in range(RAYS))
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {S} {S}" width="{S}" height="{S}">
<title>Claudemon</title>
<defs>
  <linearGradient id="bg" x1="0" y1="0" x2="0" y2="{S}" gradientUnits="userSpaceOnUse">
    <stop offset="0" stop-color="#2a2320"/>
    <stop offset=".52" stop-color="#191514"/>
    <stop offset="1" stop-color="#100e0d"/>
  </linearGradient>
  <radialGradient id="glow" cx="{CX}" cy="{CY}" r="360" gradientUnits="userSpaceOnUse">
    <stop offset="0" stop-color="#d97757" stop-opacity=".34"/>
    <stop offset=".5" stop-color="#d97757" stop-opacity=".10"/>
    <stop offset="1" stop-color="#d97757" stop-opacity="0"/>
  </radialGradient>
  <linearGradient id="mark" x1="0" y1="{CY - R_TIP}" x2="0" y2="{CY + R_TIP}" gradientUnits="userSpaceOnUse">
    <stop offset="0" stop-color="#f8ad8b"/>
    <stop offset=".5" stop-color="#e57e53"/>
    <stop offset="1" stop-color="#c9552d"/>
  </linearGradient>
  <!-- the flat run is a dim trace; only the beat under the mark is live -->
  <linearGradient id="sig" x1="240" y1="0" x2="784" y2="0" gradientUnits="userSpaceOnUse">
    <stop offset="0" stop-color="#ffb02e" stop-opacity="0"/>
    <stop offset=".07" stop-color="#ffb02e" stop-opacity=".60"/>
    <stop offset=".31" stop-color="#ffb02e" stop-opacity=".60"/>
    <stop offset=".38" stop-color="#ffc24e" stop-opacity="1"/>
    <stop offset=".60" stop-color="#ffc24e" stop-opacity="1"/>
    <stop offset=".67" stop-color="#ffb02e" stop-opacity=".60"/>
    <stop offset=".93" stop-color="#ffb02e" stop-opacity=".60"/>
    <stop offset="1" stop-color="#ffb02e" stop-opacity="0"/>
  </linearGradient>
  <filter id="lift" x="-30%" y="-30%" width="160%" height="160%">
    <feDropShadow dx="0" dy="7" stdDeviation="11" flood-color="#0b0807" flood-opacity=".5"/>
  </filter>
</defs>
<rect width="{S}" height="{S}" fill="url(#bg)"/>
<rect width="{S}" height="{S}" fill="url(#glow)"/>
<path d="{TRACE}" fill="none" stroke="url(#sig)" stroke-width="{TRACE_W}"
      stroke-linecap="round" stroke-linejoin="round"/>
<g filter="url(#lift)">
  <path d="{burst}" fill="none" stroke="url(#mark)" stroke-width="{RAYW}" stroke-linecap="round"/>
  <circle cx="{CX}" cy="{CY}" r="{HUB}" fill="url(#mark)"/>
</g>
</svg>
"""


# ---------------------------------------------------------------- png

def png_read(path: pathlib.Path) -> tuple[int, int, bytearray]:
    """Enough of a PNG reader for a browser screenshot: 8 bits per channel, RGB or RGBA,
    not interlaced. Returns straight RGBA rows."""
    raw = path.read_bytes()
    if raw[:8] != b"\x89PNG\r\n\x1a\n":
        sys.exit(f"{path} is not a PNG")
    pos, idat, hdr = 8, bytearray(), None
    while pos < len(raw):
        ln = struct.unpack(">I", raw[pos:pos + 4])[0]
        kind, body = raw[pos + 4:pos + 8], raw[pos + 8:pos + 8 + ln]
        if kind == b"IHDR":
            hdr = struct.unpack(">IIBBBBB", body)
        elif kind == b"IDAT":
            idat += body
        elif kind == b"IEND":
            break
        pos += 12 + ln
    w, h, depth, ctype, _, _, interlace = hdr
    if depth != 8 or ctype not in (2, 6) or interlace:
        sys.exit(f"unsupported PNG (depth {depth}, colour type {ctype}, interlace {interlace})")
    src = zlib.decompress(bytes(idat))
    bpp = 3 if ctype == 2 else 4
    stride = w * bpp
    out, prev, pos = bytearray(), bytearray(stride), 0
    for _ in range(h):
        ft, line = src[pos], bytearray(src[pos + 1:pos + 1 + stride])
        pos += 1 + stride
        for i in range(stride):
            a = line[i - bpp] if i >= bpp else 0
            b = prev[i]
            if ft == 1:
                line[i] = (line[i] + a) & 255
            elif ft == 2:
                line[i] = (line[i] + b) & 255
            elif ft == 3:
                line[i] = (line[i] + (a + b) // 2) & 255
            elif ft == 4:
                c = prev[i - bpp] if i >= bpp else 0
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                line[i] = (line[i] + (a if pa <= pb and pa <= pc else b if pb <= pc else c)) & 255
        prev = line
        if bpp == 4:
            out += line
        else:
            for i in range(0, stride, 3):
                out += line[i:i + 3] + b"\xff"
    return w, h, out


def png_write(path: pathlib.Path, w: int, h: int, px: bytearray) -> None:
    stride = w * 4
    raw, prev = bytearray(), bytes(stride)
    for y in range(h):
        line = bytes(px[y * stride:(y + 1) * stride])
        left = b"\0\0\0\0" + line[:-4]
        up_left = b"\0\0\0\0" + prev[:-4]
        cands = [
            (0, line),
            (1, bytes((v - a) & 255 for v, a in zip(line, left))),
            (2, bytes((v - b) & 255 for v, b in zip(line, prev))),
            (4, bytes((v - paeth(a, b, c)) & 255
                      for v, a, b, c in zip(line, left, prev, up_left))),
        ]
        ft, best = min(cands, key=lambda c: sum(v if v < 128 else 256 - v for v in c[1]))
        raw += bytes([ft]) + best
        prev = line

    def chunk(kind: bytes, body: bytes) -> bytes:
        return (struct.pack(">I", len(body)) + kind + body
                + struct.pack(">I", zlib.crc32(kind + body) & 0xFFFFFFFF))

    path.write_bytes(b"\x89PNG\r\n\x1a\n"
                     + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
                     + chunk(b"IDAT", zlib.compress(bytes(raw), 9))
                     + chunk(b"IEND", b""))


def paeth(a: int, b: int, c: int) -> int:
    p = a + b - c
    pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
    return a if pa <= pb and pa <= pc else b if pb <= pc else c


def squircle(px: bytearray, size: int) -> None:
    """Cuts the square render to the squircle and lays the rim light along its top edge.
    Only the pixels the curve actually runs through get supersampled - the rest are
    plainly inside or plainly outside."""
    half = size / 2.0
    step = 1.0 / 4

    def field(x: float, y: float) -> float:
        nx, ny = abs(x / half - 1.0), abs(y / half - 1.0)
        return nx ** N + ny ** N

    for y in range(size):
        for x in range(size):
            f = field(x + 0.5, y + 0.5)
            if f < 0.88:
                cov = 1.0
            elif f > 1.14:
                cov = 0.0
            else:
                hit = 0
                for sy in range(4):
                    for sx in range(4):
                        if field(x + (sx + 0.5) * step, y + (sy + 0.5) * step) <= 1.0:
                            hit += 1
                cov = hit / 16.0
            i = (y * size + x) * 4
            if cov < 1.0:
                px[i + 3] = int(round(px[i + 3] * cov))
            if cov <= 0.0:
                continue
            g = f ** (1.0 / N)           # 0 at the centre, 1 on the edge
            if g < RIM_FROM:
                continue
            ny = y / half - 1.0
            top = max(0.0, min(1.0, (-ny + 0.15) / 0.9))
            if top <= 0.0:
                continue
            band = (g - RIM_FROM) / (1.0 - RIM_FROM)
            k = RIM_ALPHA * top * math.sin(math.pi * min(band, 1.0)) * cov
            for c in range(3):
                px[i + c] = min(255, int(round(px[i + c] + (255 - px[i + c]) * k)))


def resize(px: bytearray, size: int, out: int) -> bytearray:
    """Area-average box filter, fractional edges included - 1024 does not divide by 180.
    The average runs on premultiplied alpha so the transparent corners cannot bleed grey
    into the pixels along the curve."""
    if out == size:
        return px
    scale = size / out
    spans = []
    for i in range(out):
        lo, hi = i * scale, (i + 1) * scale
        span = []
        for j in range(int(lo), min(size, math.ceil(hi))):
            span.append((j, min(hi, j + 1) - max(lo, j)))
        spans.append(span)

    wide = bytearray(out * size * 4)          # horizontal pass
    for y in range(size):
        row = y * size
        for x, span in enumerate(spans):
            r = g = b = al = 0.0
            for j, f in span:
                i = (row + j) * 4
                a = px[i + 3] * f
                r += px[i] * a
                g += px[i + 1] * a
                b += px[i + 2] * a
                al += a
            o = (y * out + x) * 4
            wide[o + 3] = round(al / scale)
            if al:
                wide[o] = min(255, round(r / al))
                wide[o + 1] = min(255, round(g / al))
                wide[o + 2] = min(255, round(b / al))

    dst = bytearray(out * out * 4)            # vertical pass
    for y, span in enumerate(spans):
        for x in range(out):
            r = g = b = al = 0.0
            for j, f in span:
                i = ((j * out) + x) * 4
                a = wide[i + 3] * f
                r += wide[i] * a
                g += wide[i + 1] * a
                b += wide[i + 2] * a
                al += a
            o = (y * out + x) * 4
            dst[o + 3] = round(al / scale)
            if al:
                dst[o] = min(255, round(r / al))
                dst[o + 1] = min(255, round(g / al))
                dst[o + 2] = min(255, round(b / al))
    return dst


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("step", choices=("svg", "png"))
    ap.add_argument("shot", nargs="?", help="1024x1024 render of icon.svg (step `png`)")
    args = ap.parse_args()

    ASSETS.mkdir(exist_ok=True)
    if args.step == "svg":
        (ASSETS / "icon.svg").write_text(build_svg())
        print(f"wrote {ASSETS / 'icon.svg'}")
        return

    if not args.shot:
        ap.error("step `png` needs the rendered square")
    w, h, px = png_read(pathlib.Path(args.shot))
    if (w, h) != (S, S):
        sys.exit(f"expected a {S}x{S} render, got {w}x{h}")
    squircle(px, S)
    for size in SIZES:
        out = ASSETS / f"icon-{size}.png"
        png_write(out, size, size, resize(px, S, size))
        print(f"wrote {out}  ({out.stat().st_size // 1024} kB)")


if __name__ == "__main__":
    main()
