#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Generate a cropped, one-tikzpicture-per-page preview of LaTeX/TikZ figures.

Each ``tikzpicture`` becomes its own tightly-cropped page via the ``standalone``
class with ``multi=tikzpicture,crop``. Render the result to PNG (pdftoppm) and
inspect each figure with no page whitespace.

Usage:
    python gen_figcrop.py --root . --glob "figures/**/*.tex" \
        --preamble figcrop_preamble.tex --out _figcrop.tex

--preamble : file whose contents are injected before \\begin{document}
             (the project's \\input{preamble}, macros, and any \\def the figures
             assume). If omitted, a minimal tikz preamble is used.
--out      : output .tex (compile it from --root so relative \\input paths resolve).

Writes <out-dir>/figcrop_map.txt: "PAGE<TAB>figure-file" (page N = that file).
Warns if a file contains 0 or >1 tikzpicture (page numbering assumes exactly 1).
"""
import argparse, glob, os, re, sys

MINIMAL_PREAMBLE = r"""\usepackage{tikz}
\usepackage{amsmath,amssymb}
\usetikzlibrary{arrows.meta,calc,positioning,decorations.pathreplacing}"""


def natural_key(p):
    # sort by the integer runs in the path so L2_F10 sorts after L2_F2
    return [int(s) if s.isdigit() else s.lower() for s in re.split(r'(\d+)', p)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--root', default='.', help='project root (cwd for the compile)')
    ap.add_argument('--glob', required=True, help='figure glob, e.g. "figures/**/*.tex"')
    ap.add_argument('--preamble', default=None, help='file with preamble setup lines')
    ap.add_argument('--out', default='_figcrop.tex')
    ap.add_argument('--border', default='9pt')
    args = ap.parse_args()

    os.chdir(args.root)
    files = sorted(glob.glob(args.glob, recursive=True), key=natural_key)
    if not files:
        sys.exit(f'no figures matched {args.glob!r} under {os.getcwd()}')

    if args.preamble and os.path.exists(args.preamble):
        preamble = open(args.preamble, encoding='utf-8').read().rstrip()
    else:
        preamble = MINIMAL_PREAMBLE
        if args.preamble:
            print(f'(warning: {args.preamble} not found; using minimal preamble)')

    head = (f'\\documentclass[border={args.border},multi=tikzpicture,crop]{{standalone}}\n'
            f'{preamble}\n\\begin{{document}}\n')
    body, page, mapping, warned = [], 0, [], 0
    for f in files:
        rel = os.path.splitext(f.replace('\\', '/'))[0]
        txt = open(f, encoding='utf-8', errors='replace').read()
        n = txt.count(r'\begin{tikzpicture}')
        if n != 1:
            warned += 1
            print(f'(warning: {f} has {n} tikzpicture(s); page map may be off)')
        for _ in range(max(n, 1)):
            page += 1
            mapping.append((page, os.path.basename(rel)))
        body.append(f'\\input{{{rel}}}')
    out_dir = os.path.dirname(os.path.abspath(args.out)) or '.'
    open(args.out, 'w', encoding='utf-8').write(head + '\n'.join(body) + '\n\\end{document}\n')

    mappath = os.path.join('build' if os.path.isdir('build') else out_dir, 'figcrop_map.txt')
    os.makedirs(os.path.dirname(mappath) or '.', exist_ok=True)
    open(mappath, 'w', encoding='utf-8').write(
        '\n'.join(f'{p:03d}\t{name}' for p, name in mapping) + '\n')

    print(f'figures: {len(files)}  pages(by tikzpicture): {page}')
    print(f'wrote {args.out}  +  page map: {mappath}')
    if warned:
        print(f'note: {warned} file(s) did not have exactly 1 tikzpicture (see warnings).')


if __name__ == '__main__':
    main()
