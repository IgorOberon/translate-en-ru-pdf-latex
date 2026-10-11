#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Rank TikZ figures by overlap/transparency risk to triage a large set.

Heuristic: figures that combine many text-width nodes, multiple scopes, bold
"title" nodes, and very faint fills are the ones most likely to have collisions
or low-contrast problems. Inspect the top of the list first; simple single-vector
diagrams almost always render clean.

Usage:  python score_figures.py --glob "figures/**/*.tex" [--top 40]
"""
import argparse, glob, os, re, sys


def score(text):
    tw      = text.count('text width')                       # multi-line boxes
    scopes  = text.count(r'\begin{scope}')                   # multi-panel
    titles  = len(re.findall(r'\\node\[[^\]]*bfseries', text))  # hardcoded titles
    faint   = len(re.findall(r'fill=\w+!([1-9]|10)\b', text))   # fills <=10% (faint)
    op      = len(re.findall(r'opacity=0\.[1-5]\b', text))      # low opacity marks
    s = tw * 2 + scopes * 2 + titles * 2 + faint + op
    return s, tw, scopes, titles, faint, op


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--glob', required=True)
    ap.add_argument('--top', type=int, default=40)
    args = ap.parse_args()
    rows = []
    for f in glob.glob(args.glob, recursive=True):
        t = open(f, encoding='utf-8', errors='replace').read()
        rows.append((score(t), os.path.basename(f)[:-4]))
    rows.sort(key=lambda r: r[0][0], reverse=True)
    print(f'{"score":>5}  {"figure":34s} | tw scope title faint op')
    for (s, tw, sc, ti, fa, op), name in rows[:args.top]:
        print(f'{s:5d}  {name:34s} | {tw} {sc} {ti} {fa} {op}')
    print(f'\n({len(rows)} figures total; inspect high scores first)')


if __name__ == '__main__':
    main()
