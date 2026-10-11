#!/usr/bin/env python3
"""Sample the background colour around a label region of a raster figure.

Scanned/extracted book figures are almost never pure white — the background
is cream, light grey, or a JPEG-noisy shade. A white patch over a label
therefore shows as a bright rectangle. This tool samples the pixels in a
band AROUND the given rectangle (where the background is visible next to
the old label), takes the per-channel median (robust to line-art strokes
crossing the band), and prints a ready \\definecolor line for the overlay.

Coordinates are RELATIVE (0..1, origin bottom-left — same convention as the
TikZ overlay scope), so numbers move straight between this tool, labels.tsv
and the generated overlay.

Usage:
  py -3 scripts/sample_bg.py fig.jpg --rect 0.28 0.66 0.44 0.72
  py -3 scripts/sample_bg.py fig.jpg --rect 0.28 0.66 0.44 0.72 --name figbg2
  py -3 scripts/sample_bg.py fig.jpg --at 0.36 0.69          # small square probe

Needs Pillow (pip install pillow).
"""
import argparse
import statistics
import sys

print(">> sample_bg.py v1 loaded", flush=True)

try:
    from PIL import Image
except ImportError:
    print("!! Pillow required:  pip install pillow")
    sys.exit(1)


def main():
    ap = argparse.ArgumentParser(
        description="Median background colour around a label bbox -> \\definecolor for the overlay patch.")
    ap.add_argument("image", help="raster figure (jpg/png)")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--rect", nargs=4, type=float, metavar=("X0", "Y0", "X1", "Y1"),
                   help="label bbox, relative 0..1, origin bottom-left; a band around it is sampled")
    g.add_argument("--at", nargs=2, type=float, metavar=("X", "Y"),
                   help="probe a small square centred at this relative point")
    ap.add_argument("--band", type=float, default=0.012,
                    help="band/probe half-width as a fraction of image width (default %(default)s)")
    ap.add_argument("--name", default="figbg", help="colour name to define (default %(default)s)")
    args = ap.parse_args()

    im = Image.open(args.image).convert("RGB")
    W, H = im.size
    b = max(2, int(args.band * W))

    def to_px(x, y):
        # relative (origin bottom-left) -> pixel (origin top-left)
        return int(x * W), int((1 - y) * H)

    px = []
    if args.rect:
        x0, y0, x1, y1 = args.rect
        (X0, Y1), (X1, Y0) = to_px(x0, y0), to_px(x1, y1)   # note y flip
        X0o, Y0o, X1o, Y1o = X0 - b, Y0 - b, X1 + b, Y1 + b
        for X in range(max(0, X0o), min(W, X1o)):
            for Y in range(max(0, Y0o), min(H, Y1o)):
                inside = X0 <= X < X1 and Y0 <= Y < Y1
                if not inside:                      # band only, not the label itself
                    px.append(im.getpixel((X, Y)))
    else:
        X, Y = to_px(*args.at)
        for dx in range(-b, b + 1):
            for dy in range(-b, b + 1):
                if 0 <= X + dx < W and 0 <= Y + dy < H:
                    px.append(im.getpixel((X + dx, Y + dy)))

    if not px:
        print("!! empty sample region"); sys.exit(1)
    r = round(statistics.median(p[0] for p in px))
    g_ = round(statistics.median(p[1] for p in px))
    b_ = round(statistics.median(p[2] for p in px))
    print(f"median RGB over {len(px)} px:  {r},{g_},{b_}")
    print(f"\\definecolor{{{args.name}}}{{RGB}}{{{r},{g_},{b_}}}")


if __name__ == "__main__":
    main()
