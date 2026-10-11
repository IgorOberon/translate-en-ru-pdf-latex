#!/usr/bin/env python3
"""Passport probe for a reference (scanned) PDF.

Prints: total pages, outline/bookmarks presence (and a preview), whether a
text layer exists — with a warning that OCR text layers of scans are NOT to
be trusted (formulas and digits come out wrong). Optionally renders selected
pages to PNG for visual reading.

Usage:
  python scripts/ref_probe.py book.pdf
  python scripts/ref_probe.py book.pdf --render "5-9,12" --out out/ --dpi 120
"""
import argparse
import sys
from pathlib import Path

print(">> ref_probe.py v1", flush=True)


def parse_ranges(spec: str):
    pages = []
    for part in spec.split(","):
        part = part.strip()
        if "-" in part:
            a, b = part.split("-", 1)
            pages.extend(range(int(a), int(b) + 1))
        elif part:
            pages.append(int(part))
    return sorted(set(pages))


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pdf", help="reference PDF (read-only)")
    ap.add_argument("--render", default=None,
                    help='pages to render as PNG, 1-based: "5-9" or "1,3,7-9"')
    ap.add_argument("--out", default="out", help="output dir for PNGs")
    ap.add_argument("--dpi", type=int, default=120, help="render resolution")
    a = ap.parse_args()

    import fitz
    doc = fitz.open(a.pdf)
    print(f"file           : {a.pdf}")
    print(f"pages          : {len(doc)}")

    toc = doc.get_toc(simple=True)
    print(f"bookmarks      : {'yes, ' + str(len(toc)) + ' entries' if toc else 'no'}")
    for lvl, title, page in toc[:15]:
        print(f"  {'  ' * (lvl - 1)}[{page}] {title}")
    if len(toc) > 15:
        print(f"  ... and {len(toc) - 15} more")

    sample = "".join(doc[i].get_text() for i in range(min(10, len(doc))))
    has_text = len(sample.strip()) > 100
    print(f"text layer     : {'present' if has_text else 'absent/empty'}")
    if has_text:
        print("?? WARNING: this is a scan — the text layer is OCR output and is "
              "NOT reliable (formulas, digits and diacritics come out wrong). "
              "Read pages visually via --render instead of trusting it.")

    if a.render:
        outdir = Path(a.out)
        outdir.mkdir(parents=True, exist_ok=True)
        for p in parse_ranges(a.render):
            if not 1 <= p <= len(doc):
                print(f"?? page {p} out of range, skipped")
                continue
            pix = doc[p - 1].get_pixmap(dpi=a.dpi)
            f = outdir / f"page_{p:04d}.png"
            pix.save(str(f))
            print(f"rendered       : {f}")
    doc.close()


if __name__ == "__main__":
    main()
