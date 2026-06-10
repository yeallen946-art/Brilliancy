"""Build the cburnett piece asset catalog for the app (UI_FLOW §4.1).

Converts the 12 cburnett SVGs to vector PDFs and writes App/Resources/Assets.xcassets
with one imageset per piece (preserves-vector-representation, so they stay crisp at any
size). Run from pipeline/. Source SVGs default to the local cburnett download.

Attribution: cburnett by Colin M.L. Burnett, CC BY-SA 3.0 (see App/Resources/PIECES_LICENSE).
"""

from __future__ import annotations

import json
import os
import sys

from reportlab.graphics import renderPDF
from svglib.svglib import svg2rlg

CODES = ["wP", "wN", "wB", "wR", "wQ", "wK", "bP", "bN", "bB", "bR", "bQ", "bK"]


def main(src_dir: str) -> int:
    out = os.path.normpath(os.path.join(
        os.path.dirname(__file__), "..", "..", "App", "Resources", "Assets.xcassets"))
    os.makedirs(out, exist_ok=True)

    with open(os.path.join(out, "Contents.json"), "w", encoding="utf-8", newline="\n") as fh:
        json.dump({"info": {"author": "xcode", "version": 1}}, fh, indent=2)

    for code in CODES:
        svg = os.path.join(src_dir, f"{code}.svg")
        if not os.path.exists(svg):
            print(f"missing {svg}", file=sys.stderr)
            return 1
        iset = os.path.join(out, f"piece_{code}.imageset")
        os.makedirs(iset, exist_ok=True)
        renderPDF.drawToFile(svg2rlg(svg), os.path.join(iset, f"{code}.pdf"))
        contents = {
            "images": [{"idiom": "universal", "filename": f"{code}.pdf"}],
            "info": {"author": "xcode", "version": 1},
            "properties": {
                "preserves-vector-representation": True,
                "template-rendering-intent": "original",
            },
        }
        with open(os.path.join(iset, "Contents.json"), "w", encoding="utf-8", newline="\n") as fh:
            json.dump(contents, fh, indent=2)
        print(f"wrote piece_{code}.imageset")

    print(f"\nAsset catalog at {out}")
    return 0


if __name__ == "__main__":
    default_src = os.path.normpath(os.path.join(
        os.path.dirname(__file__), "..", "..", "art", "cburnett"))
    raise SystemExit(main(sys.argv[1] if len(sys.argv) > 1 else default_src))
