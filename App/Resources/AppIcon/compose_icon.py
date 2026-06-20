"""Build the Brilliancy app icon from the chosen knight render.

Pipeline (Jerry, 2026-06-17): the gold knight was generated with an OpenRouter
image model (see gen_variations.py, variant "v4") on a green ground. This script
chroma-keys the knight off the green, drops it onto a deep navy radial-gradient
background with a soft cast shadow, and writes the final 1024x1024 opaque PNG.

Deterministic: re-run to rebuild icon-1024.png from source_knight.png.
The upstream AI generation itself is NOT deterministic — source_knight.png is the
committed input of record.

Run from App/:  python Resources/AppIcon/compose_icon.py
"""
from __future__ import annotations
import math
from pathlib import Path
from PIL import Image, ImageChops, ImageFilter

HERE = Path(__file__).resolve().parent
SRC = HERE / "source_knight.png"
OUT = HERE.parent / "Assets.xcassets" / "AppIcon.appiconset" / "icon-1024.png"

BG_CORE = (42, 52, 76)   # navy, lighter optical center
BG_EDGE = (11, 16, 33)   # near-black edges (vignette)


def radial(size, core, edge):
    r0 = 384
    im = Image.new("RGB", (r0, r0))
    px = im.load()
    cx, cy = r0 / 2, r0 * 0.42
    md = math.hypot(max(cx, r0 - cx), max(cy, r0 - cy))
    for y in range(r0):
        for x in range(r0):
            d = (math.hypot(x - cx, y - cy) / md) ** 1.3
            px[x, y] = tuple(round(core[i] + (edge[i] - core[i]) * d) for i in range(3))
    return im.resize((size, size), Image.LANCZOS)


def main():
    src = Image.open(SRC).convert("RGB")
    w, h = src.size
    hue, sat, _ = src.convert("HSV").split()

    # Green background = green hue band & decent saturation. Gold (hue ~30) and the
    # white "!!" (low saturation) fall outside, so they survive as foreground.
    green = ImageChops.multiply(
        hue.point(lambda v: 255 if 60 <= v <= 150 else 0),
        sat.point(lambda v: 255 if v >= 45 else 0),
    )
    alpha = ImageChops.invert(green)
    alpha = alpha.filter(ImageFilter.MedianFilter(5))    # despeckle
    alpha = alpha.filter(ImageFilter.MinFilter(3))       # erode 1px -> kill green fringe
    alpha = alpha.filter(ImageFilter.GaussianBlur(1.0))  # feather

    bg = radial(w, BG_CORE, BG_EDGE)
    shadow = alpha.point(lambda a: int(a * 0.5))
    shadow = ImageChops.offset(shadow, 0, 18).filter(ImageFilter.GaussianBlur(14))
    bg = Image.composite(Image.new("RGB", (w, h), (0, 0, 0)), bg, shadow)

    bg.paste(src, (0, 0), alpha)
    bg = bg.resize((1024, 1024), Image.LANCZOS)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    bg.save(OUT)  # opaque, no alpha (App Store requirement)
    print("wrote", OUT)


if __name__ == "__main__":
    main()
