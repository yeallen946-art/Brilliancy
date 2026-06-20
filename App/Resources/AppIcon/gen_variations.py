"""One-off: generate app-icon variations via OpenRouter image model.

Saves to Resources/AppIcon/_ai/. Reads OPENROUTER_API_KEY from pipeline/.env.
"""
from __future__ import annotations
import base64, json, urllib.request
from pathlib import Path

ENV = Path(__file__).resolve().parents[3] / "pipeline" / ".env"
OUTDIR = Path(__file__).resolve().parent / "_ai"
MODEL = "google/gemini-3-pro-image"

BASE = ("iOS app icon for a premium chess training app. Flat app-icon composition, "
        "full-bleed square 1:1, NO rounded corners, no border, no extra text. "
        "High resolution, App Store quality. ")

VARIANTS = {
    "v1_silver": BASE + ("A single elegant knight chess piece in polished platinum "
        "silver with brushed-metal finish and soft studio highlights, centered on a "
        "deep navy radial-gradient background, small tasteful white \"!!\" mark top-right."),
    "v2_front": BASE + ("A gold knight chess piece seen from a dynamic three-quarter "
        "front angle, glossy metallic finish, dramatic studio lighting, centered on a "
        "dark slate radial-gradient background, small white \"!!\" mark top-right."),
    "v3_nobase": BASE + ("Just a bold stylized gold knight head (no base), large and "
        "filling the frame, smooth polished metal with rim light, on a deep navy "
        "background, small white \"!!\" mark top-right, very minimal and modern."),
    "v4_emerald": BASE + ("A polished gold knight chess piece centered on a deep "
        "emerald-green radial-gradient background with a subtle soft vignette, luxurious "
        "and elegant, small cream-white \"!!\" mark top-right."),
    "v5_charcoal_nomark": BASE + ("A single gold knight chess piece with warm amber "
        "studio lighting and gentle reflections, centered on a near-black charcoal "
        "background with a warm glow behind it, ultra minimal, no extra marks."),
    "v6_emblem": BASE + ("A gold knight chess piece embossed as a luxury medallion "
        "emblem, raised relief with soft bevel and highlights, on a dark textured navy "
        "disc, premium crest style, small white \"!!\" mark top-right."),
}


def load_key():
    for line in ENV.read_text(encoding="utf-8").splitlines():
        if line.startswith("OPENROUTER_API_KEY="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    raise SystemExit("no key")


def main():
    key = load_key()
    OUTDIR.mkdir(parents=True, exist_ok=True)
    for name, prompt in VARIANTS.items():
        body = json.dumps({"model": MODEL, "messages": [{"role": "user", "content": prompt}],
                           "modalities": ["image", "text"]}).encode()
        req = urllib.request.Request("https://openrouter.ai/api/v1/chat/completions", data=body,
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=180) as r:
                data = json.load(r)
            imgs = data.get("choices", [{}])[0].get("message", {}).get("images") or []
            if not imgs:
                print(name, "NO IMAGE"); continue
            url = imgs[0].get("image_url", {}).get("url", "")
            (OUTDIR / f"{name}.png").write_bytes(base64.b64decode(url.split(",", 1)[1]))
            print("wrote", name)
        except Exception as e:
            print(name, "ERR", e)


if __name__ == "__main__":
    main()
