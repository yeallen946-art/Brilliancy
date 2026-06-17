"""Generate the Brilliancy app icon (1024x1024, opaque, no alpha).

Concept (Jerry, 2026-06-17): knight silhouette + the "!!" brilliancy annotation,
amber-on-slate to read as "chess" + "the brilliant move". Single-size iOS icon.

Run from App/:  python Resources/AppIcon/make_icon.py
Deterministic — re-run to regenerate the PNG after tweaking constants.
"""
from __future__ import annotations
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageFilter

S = 1024
OUT = Path(__file__).resolve().parents[1] / "Assets.xcassets" / "AppIcon.appiconset" / "icon-1024.png"

# Palette — deep slate board + amber piece (matches in-app accent).
TOP = (40, 54, 74)        # #28364a
BOTTOM = (18, 25, 37)     # #121925
AMBER = (245, 185, 66)    # #f5b942
WHITE = (255, 255, 255)

KNIGHT_FONT = "C:/Windows/Fonts/seguisym.ttf"   # Segoe UI Symbol has U+265E
MARK_FONT = "C:/Windows/Fonts/georgiab.ttf"     # Georgia Bold for "!!"


def vertical_gradient(size: int, top, bottom) -> Image.Image:
    base = Image.new("RGB", (1, size))
    px = base.load()
    for y in range(size):
        t = y / (size - 1)
        px[0, y] = tuple(round(a + (b - a) * t) for a, b in zip(top, bottom))
    return base.resize((size, size))


def main() -> None:
    img = vertical_gradient(S, TOP, BOTTOM).convert("RGBA")

    # Soft amber glow behind the piece for depth.
    glow = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    gd.ellipse([S * 0.18, S * 0.28, S * 0.82, S * 0.92], fill=AMBER + (70,))
    glow = glow.filter(ImageFilter.GaussianBlur(90))
    img = Image.alpha_composite(img, glow)

    draw = ImageDraw.Draw(img)

    # Knight glyph ♞ — solid, amber, sitting low-left of center.
    knight_font = ImageFont.truetype(KNIGHT_FONT, 720)
    glyph = "♞"
    bbox = draw.textbbox((0, 0), glyph, font=knight_font)
    gw, gh = bbox[2] - bbox[0], bbox[3] - bbox[1]
    kx = S * 0.50 - gw / 2 - bbox[0]
    ky = S * 0.56 - gh / 2 - bbox[1]
    draw.text((kx, ky), glyph, font=knight_font, fill=AMBER)

    # "!!" brilliancy mark, white, top-right corner.
    mark_font = ImageFont.truetype(MARK_FONT, 300)
    mb = draw.textbbox((0, 0), "!!", font=mark_font)
    mw = mb[2] - mb[0]
    draw.text((S * 0.92 - mw - mb[0], S * 0.06 - mb[1]), "!!", font=mark_font, fill=WHITE)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    img.convert("RGB").save(OUT)  # flatten -> opaque, no alpha (App Store requirement)
    print("wrote", OUT)


if __name__ == "__main__":
    main()
