#!/usr/bin/env python3
"""Generate LaTeX overlay blocks (tikzpicture over \\includegraphics) from labels.tsv.

The label registry is the resumable, reviewable heart of the workflow: one
row per translated in-figure label. This tool turns it into ready-to-paste
(or \\input-able) LaTeX — an image node plus, for every label, an optional
background patch and a text node in RELATIVE coordinates 0..1 (origin
bottom-left), so the overlay survives any later change of the printed width.

labels.tsv columns (TAB-separated, # starts a comment line):
  figure      image file as used by \\includegraphics (groups rows)
  text_src    original label (for review; not typeset)
  text_target replacement text, raw LaTeX allowed (e.g. равные \\(\\Phi\\))
  x  y        anchor point, relative 0..1
  anchor      TikZ anchor (center, west, south west, ...)
  rotate      degrees CCW (0 for none)
  size        LaTeX size command w/o backslash (small, footnotesize, ...); empty = normal
  status      todo | done | skip  (skip rows are omitted, others emitted)
  patch       OPTIONAL x0,y0,x1,y1 rectangle to fill with the bg colour BEFORE
              the node; empty = rely on the node's own fill to cover the original
  bgcolor     OPTIONAL colour name (default figbg) — labels on different
              backgrounds in one figure need different sampled colours

Usage:
  py -3 scripts/labels_to_tikz.py labels.tsv > overlays.tex
  py -3 scripts/labels_to_tikz.py labels.tsv --width 0.8\\linewidth --only fig1.jpg

stdlib only. Define the colours first (scripts/sample_bg.py prints them).
"""
import argparse
import csv
import sys

print(">> labels_to_tikz.py v1 loaded", file=sys.stderr, flush=True)

REQUIRED = ["figure", "text_src", "text_target", "x", "y",
            "anchor", "rotate", "size", "status"]


def main():
    ap = argparse.ArgumentParser(
        description="labels.tsv -> tikzpicture overlay blocks (relative 0..1 coords).")
    ap.add_argument("tsv", help="label registry (TSV)")
    ap.add_argument("--width", default="\\linewidth",
                    help="\\includegraphics width (default %(default)s)")
    ap.add_argument("--only", default=None, help="emit just this figure")
    args = ap.parse_args()

    rows = []
    with open(args.tsv, encoding="utf-8", newline="") as f:
        rdr = csv.DictReader(
            (ln for ln in f if not ln.lstrip().startswith("#")), delimiter="\t")
        missing = [c for c in REQUIRED if c not in (rdr.fieldnames or [])]
        if missing:
            sys.exit(f"!! labels.tsv is missing columns: {', '.join(missing)}")
        rows = [r for r in rdr if r["figure"]]

    figures = {}
    for r in rows:
        if args.only and r["figure"] != args.only:
            continue
        if r["status"].strip() == "skip":
            continue
        figures.setdefault(r["figure"], []).append(r)

    if not figures:
        sys.exit("!! nothing to emit (check figure names / --only / status)")

    out = []
    for fig, labels in figures.items():
        out.append(f"% ---- {fig}: {len(labels)} label(s) ----")
        out.append("\\begin{tikzpicture}")
        out.append(f"  \\node[anchor=south west,inner sep=0] (img)"
                   f" {{\\includegraphics[width={args.width}]{{{fig}}}}};")
        out.append("  \\begin{scope}[x={(img.south east)},y={(img.north west)}]")
        for r in labels:
            bg = (r.get("bgcolor") or "").strip() or "figbg"
            patch = (r.get("patch") or "").strip()
            if patch:
                x0, y0, x1, y1 = (v.strip() for v in patch.split(","))
                out.append(f"    \\fill[{bg}] ({x0},{y0}) rectangle ({x1},{y1});")
            font = f",font=\\{r['size'].strip()}" if r["size"].strip() else ""
            rot = f",rotate={r['rotate'].strip()}" if r["rotate"].strip() not in ("", "0") else ""
            out.append(f"    \\node[anchor={r['anchor'].strip()},fill={bg},"
                       f"inner sep=1pt{font}{rot}]"
                       f" at ({r['x'].strip()},{r['y'].strip()})"
                       f" {{{r['text_target']}}};  % was: {r['text_src']}")
        out.append("  \\end{scope}")
        out.append("\\end{tikzpicture}")
        out.append("")
    print("\n".join(out))


if __name__ == "__main__":
    main()
