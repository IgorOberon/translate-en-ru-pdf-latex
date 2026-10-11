#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Cross-chapter consistency sweep for a multi-chapter translation.

Stdlib only. Language-agnostic (Unicode). Reports; never edits.

  py -3 consistency_sweep.py --dir chapters --glossary glossary.tsv

glossary.tsv (tab-separated, header row skipped): --term-col N (1-based, default 3)
is the canonical target-term column to count, e.g. for a
`english <TAB> original <TAB> target <TAB> notes` glossary the target is col 3.
Rows with fewer columns fall back to their last column. A row whose line contains
KEY (case-insensitive) flags a term whose obvious cognate is dangerous — listed
for manual context review.

--names accepts a file of `Variant1|Variant2|...` lines (one name per line); if
omitted, name checking is skipped. Build it from the bibliography.
"""
import argparse, glob, os, re, sys

def read_files(d):
    out = {}
    for p in sorted(glob.glob(os.path.join(d, "*.tex")) + glob.glob(os.path.join(d, "*.md"))):
        with open(p, encoding="utf-8", errors="replace") as f:
            out[os.path.basename(p)] = f.read()
    return out

def load_glossary(path, term_col):
    terms, key_terms = [], []
    with open(path, encoding="utf-8", errors="replace") as f:
        for i, line in enumerate(f):
            if i == 0 or not line.strip():
                continue
            cols = [c.strip() for c in line.rstrip("\n").split("\t")]
            if not any(cols):
                continue
            idx = term_col - 1
            term = cols[idx] if idx < len(cols) and cols[idx] else cols[-1]
            if term and term not in terms:
                terms.append(term)
                if "KEY" in line.upper():
                    key_terms.append(term)
    return terms, key_terms

def count_all(files, needle):
    return sum(text.count(needle) for text in files.values())

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True)
    ap.add_argument("--glossary")
    ap.add_argument("--term-col", type=int, default=3,
                    help="1-based column of the canonical target term (default 3)")
    ap.add_argument("--names")
    args = ap.parse_args()

    files = read_files(args.dir)
    if not files:
        print("no .tex/.md files in", args.dir); sys.exit(1)
    print("files: %d" % len(files))

    if args.glossary:
        terms, key_terms = load_glossary(args.glossary, args.term_col)
        print("\n== TERM COUNTS (glossary canonical terms) ==")
        for t in terms:
            n = count_all(files, t)
            flag = "  <- KEY (check no forbidden cognate)" if t in key_terms else ""
            mark = "  !! ZERO" if n == 0 else ""
            print("  %-32s %4d%s%s" % (t, n, mark, flag))

    if args.names:
        print("\n== NAME TRANSLITERATION (each name should resolve to ONE spelling) ==")
        with open(args.names, encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                pat = re.compile("(" + line + ")")
                seen = {}
                for text in files.values():
                    for m in pat.findall(text):
                        seen[m] = seen.get(m, 0) + 1
                status = "OK" if len(seen) <= 1 else "!! SPLIT"
                detail = ", ".join("%s=%d" % (k, v) for k, v in sorted(seen.items()))
                print("  [%s] %s" % (status, detail or "(none found)"))

    print("\n== TYPOGRAPHY ==")
    g_open = count_all(files, "«"); g_close = count_all(files, "»")
    n_open = count_all(files, "„"); n_close = count_all(files, "“")
    print("  guillemets:  « %d   » %d   %s" % (g_open, g_close,
          "OK" if g_open == g_close else "!! UNBALANCED"))
    print("  nested:      „ %d   “ %d   %s" % (n_open, n_close,
          "OK" if n_open == n_close else "!! UNBALANCED"))

    straight = dbl = rng = 0
    straight_hits = []
    for name, text in files.items():
        for m in re.finditer(r'"[^\W\d_]', text):           # ascii quote before a letter
            straight += 1
            if len(straight_hits) < 8:
                straight_hits.append("%s: …%s…" % (name, text[max(0,m.start()-15):m.start()+15].replace("\n"," ")))
        dbl += len(re.findall(r'[^\W\d_]  +[^\W\d_]', text))  # double space between letters
        rng += len(re.findall(r'\d+-\d+', text))              # hyphen between digits
    print("  straight ASCII quotes before a letter: %d %s" % (straight, "OK" if straight==0 else "!! found"))
    for h in straight_hits:
        print("       " + h)
    print("  double spaces between letters: %d %s" % (dbl, "OK" if dbl==0 else "!! found"))
    print("  hyphen between digits (range should be -- / –): %d %s" % (rng, "OK" if rng==0 else "(review: page ranges?)"))

if __name__ == "__main__":
    main()
