#!/usr/bin/env python3
"""Overlay a RELATIVE (0..1) coordinate grid on a raster figure.

The raster counterpart of extract-pdf-figures' grid_overlay.py (which works
on PDF pages, in points): for a standalone image file you take label
coordinates in the same relative 0..1 space the TikZ overlay uses, so a
value read off this grid goes into labels.tsv verbatim. Origin is
BOTTOM-LEFT, matching the overlay scope.

Usage:
  py -3 scripts/relgrid.py fig.jpg                # -> fig.grid.png, step 0.05
  py -3 scripts/relgrid.py fig.jpg --step 0.02 --out probe.png

Needs Pillow.
"""
import argparse
import sys

print(">> relgrid.py v1 loaded", flush=True)

try:
    from PIL import Image, ImageDraw
except ImportError:
    print("!! Pillow required:  pip install pillow")
    sys.exit(1)


def main():
    ap = argparse.ArgumentParser(
        description="Draw a labelled relative 0..1 grid over a raster figure (origin bottom-left).")
    ap.add_argument("image")
    ap.add_argument("--step", type=float, default=0.05,
                    help="grid step in relative units (default %(default)s)")
    ap.add_argument("--out", default=None, help="output PNG (default <image>.grid.png)")
    args = ap.parse_args()

    im = Image.open(args.image).convert("RGB")
    W, H = im.size
    dr = ImageDraw.Draw(im)
    n = round(1 / args.step)
    for i in range(n + 1):
        t = i * args.step
        label = f"{t:.2f}".rstrip("0").rstrip(".") or "0"
        major = (abs(t * 10 - round(t * 10)) < 1e-9)  # every 0.1 = stronger line
        col = (255, 0, 0) if major else (255, 160, 160)
        X = int(t * W)
        dr.line([(X, 0), (X, H)], fill=col, width=2 if major else 1)
        Y = int((1 - t) * H)                    # relative y, origin bottom-left
        dr.line([(0, Y), (W, Y)], fill=(0, 110, 255) if major else (150, 195, 255),
                width=2 if major else 1)
        if major:
            dr.text((X + 3, 3), label, fill=(255, 0, 0))
            dr.text((3, max(0, Y - 12)), label, fill=(0, 110, 255))

    out = args.out or (args.image.rsplit(".", 1)[0] + ".grid.png")
    im.save(out)
    print(f"{args.image} ({W}x{H}) -> {out}  step={args.step}")


if __name__ == "__main__":
    main()
