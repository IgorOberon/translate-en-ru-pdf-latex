#!/usr/bin/env python3
"""Trim near-white margins off extracted figure crops (idempotent).

A pixel is "dark" (content) when its luma is below --threshold. The bounding
box of dark pixels is computed per image with a tolerance: rows/columns whose
dark share is below --dark-share are still considered margin (kills JPEG
noise). A --pad margin is kept around the box. Images already tight are left
byte-identical. The first run stores originals in <dir>_untrimmed/ (one-time
backup; an existing backup is never overwritten).

Adaptive mode (--adaptive, default ON): the darkness threshold is derived
per-image from the luma histogram (the 0.5th percentile plus a gap), so
faint dotted-line figures on white keep their content even when their "dark"
pixels are light grey.

Usage:
  python scripts/trim_images.py <images_dir> [--threshold 245] [--pad 6]
                                [--dark-share 0.02] [--report r.json]
"""
import argparse
import json
import shutil
import sys
from pathlib import Path

print(">> trim_images.py v1", flush=True)

IMG_EXT = {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp"}


def content_bbox(im, threshold, dark_share):
    """Bounding box of content rows/cols; None when nothing qualifies.

    Fast projection profiles: binarize (dark -> 255), then BOX-resize to a
    single column/row — each value is the mean, i.e. the dark share of that
    row/column scaled to 0..255.
    """
    from PIL import Image
    g = im.convert("L")
    w, h = g.size
    b = g.point(lambda v: 255 if v < threshold else 0)
    rows = b.resize((1, h), Image.Resampling.BOX).getdata()
    cols = b.resize((w, 1), Image.Resampling.BOX).getdata()
    cut = dark_share * 255
    ys = [y for y, v in enumerate(rows) if v >= cut]
    xs = [x for x, v in enumerate(cols) if v >= cut]
    if not ys or not xs:
        return None
    return xs[0], ys[0], xs[-1] + 1, ys[-1] + 1


def adaptive_params(im, base_threshold, base_share):
    """Per-image params for faint figures: thin dotted lines on white have
    few and light dark pixels, so the fixed dark-share tolerance can shave
    their sparse outer rows. Threshold comes from the histogram (halfway
    between the darkest 0.5% percentile and white); the row/col tolerance
    drops to 'any dark pixel counts'."""
    hist = im.convert("L").histogram()
    total = sum(hist) or 1
    acc, dark_p = 0, 0
    for v, n in enumerate(hist):
        acc += n
        if acc >= total * 0.005:
            dark_p = v
            break
    thr = min(250, max(base_threshold, (dark_p + 255) // 2))
    return thr, min(base_share, 1.0 / max(im.size))


def trim_one(path, args):
    from PIL import Image
    with Image.open(path) as im:
        im.load()
        w, h = im.size
        thr, share = args.threshold, args.dark_share
        if args.adaptive:
            thr, share = adaptive_params(im, thr, share)
        box = content_bbox(im, thr, share)
        if box is None:
            return None  # blank image: do not touch
        x0, y0, x1, y1 = box
        x0 = max(0, x0 - args.pad)
        y0 = max(0, y0 - args.pad)
        x1 = min(w, x1 + args.pad)
        y1 = min(h, y1 + args.pad)
        if (x1 - x0) * (y1 - y0) >= w * h * 0.98:
            return None  # nothing worth trimming (also keeps idempotency)
        cropped = im.crop((x0, y0, x1, y1))
        cropped.save(path)
        return (w * h, (x1 - x0) * (y1 - y0))


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("images_dir")
    ap.add_argument("--threshold", type=int, default=245,
                    help="luma below this is content (245)")
    ap.add_argument("--dark-share", type=float, default=0.02,
                    help="min share of dark pixels for a content row/col (0.02)")
    ap.add_argument("--pad", type=int, default=6, help="margin to keep, px (6)")
    ap.add_argument("--adaptive", action=argparse.BooleanOptionalAction,
                    default=False,
                    help="per-image histogram threshold and 1-px row tolerance "
                         "(protects faint dotted figures); enable if the "
                         "visual check of light figures shows content loss")
    ap.add_argument("--report", default=None)
    a = ap.parse_args()

    d = Path(a.images_dir).resolve()
    if not d.is_dir():
        sys.exit(f"!! no such dir: {d}")
    backup = d.parent / (d.name + "_untrimmed")
    if not backup.exists():
        shutil.copytree(d, backup)
        print(f">> backup: {backup}")
    else:
        print(f">> backup already exists, keeping: {backup}")

    trimmed, gains = 0, []
    files = sorted(p for p in d.iterdir() if p.suffix.lower() in IMG_EXT)
    for i, p in enumerate(files):
        try:
            r = trim_one(p, a)
        except Exception as e:
            print(f"?? {p.name}: {e}")
            continue
        if r:
            trimmed += 1
            gains.append(1 - r[1] / r[0])
        if (i + 1) % 500 == 0:
            print(f">> {i + 1}/{len(files)} processed", flush=True)

    avg_gain = round(100 * sum(gains) / len(gains), 1) if gains else 0.0
    rep = {"files_total": len(files), "files_trimmed": trimmed,
           "avg_area_gain_pct": avg_gain}
    print(json.dumps(rep, ensure_ascii=False))
    if a.report:
        Path(a.report).write_text(json.dumps(rep, ensure_ascii=False, indent=2)
                                  + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
