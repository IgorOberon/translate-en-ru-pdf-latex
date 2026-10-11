#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Audit a LaTeX .log for the four counts that gate a clean multi-agent join.

Usage:
    build_audit.py book.log
    build_audit.py book.tex        # will read the sibling book.log

Prints exactly:
    errors: E  undefined: U  multiply: M  missing: C
    Pages: N

The bar for a clean assembled book is all four == 0. Each is a distinct
failure surface a fanned-out build introduces:
  errors    "! ..."                         a real TeX error (stops the build)
  undefined "Reference ... undefined"       a \\ref with no \\label (dangling xref)
  multiply  "Label ... multiply defined"    a file \\input twice / dup label
  missing   "Missing character"             non-Latin text leaked into math mode
Pages comes from "Output written on ... (N pages".

Exit code 0 iff all four are zero (so it can gate a wave loop).
This only parses a log — it does not compile. Run pdflatex/lualatex first
(twice, so refs resolve), then point this at the .log.
"""
import os
import re
import sys


def find_log(arg):
    if arg.lower().endswith(".log"):
        return arg
    base = os.path.splitext(arg)[0]
    return base + ".log"


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(2)
    logfile = find_log(sys.argv[1])
    if not os.path.exists(logfile):
        print("log not found: %s (compile first)" % logfile)
        sys.exit(2)
    log = open(logfile, encoding="utf-8", errors="replace").read()

    errors = len(re.findall(r"(?m)^! ", log))
    undefined = len(re.findall(r"Reference `[^']*' on page .* undefined", log))
    # LaTeX also emits a summary line; count individual warnings, not the summary
    multiply = len(re.findall(r"Label `[^']*' multiply defined", log))
    missing = log.count("Missing character")

    m = re.search(r"Output written on \S+ \((\d+) pages?", log)
    pages = m.group(1) if m else "?"

    print("errors: %d  undefined: %d  multiply: %d  missing: %d"
          % (errors, undefined, multiply, missing))
    print("Pages: %s" % pages)

    # show a few offenders to act on, without dumping the whole log
    if errors:
        print("\n-- first errors --")
        for ln in re.findall(r"(?m)^! .*", log)[:6]:
            print("  ", ln)
    if multiply:
        print("\n-- multiply-defined labels --")
        for lbl in sorted(set(re.findall(r"Label `([^']*)' multiply defined", log)))[:12]:
            print("  ", lbl)
    if undefined:
        print("\n-- undefined references --")
        for ref in sorted(set(re.findall(r"Reference `([^']*)' on page", log)))[:12]:
            print("  ", ref)

    clean = (errors == 0 and undefined == 0 and multiply == 0 and missing == 0)
    sys.exit(0 if clean else 1)


if __name__ == "__main__":
    main()
