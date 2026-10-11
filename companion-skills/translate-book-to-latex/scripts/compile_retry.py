#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Compile a LuaLaTeX master with a retry loop for transient out-of-memory builds.

Usage:
    compile_retry.py book.tex [MAX_PASSES]

LuaTeX can intermittently die with "memory exhausted" when the system is under
RAM pressure (it loads hyphenation/babel into a single process). Re-running
usually succeeds. This runs lualatex up to MAX_PASSES (default 4) times, stops as
soon as "Output written" appears, and prints a concise health summary:
errors (`^! `), missing characters (target-script text leaked into math mode),
and `\figincl` placeholders still showing (figures not yet extracted).
"""
import os
import re
import sys
import subprocess


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    tex = sys.argv[1]
    passes = int(sys.argv[2]) if len(sys.argv) > 2 else 4
    base = os.path.splitext(os.path.basename(tex))[0]
    workdir = os.path.dirname(os.path.abspath(tex)) or "."

    log = ""
    ok = False
    for n in range(1, passes + 1):
        r = subprocess.run(
            ["lualatex", "-interaction=nonstopmode", os.path.basename(tex)],
            cwd=workdir, capture_output=True, text=True, errors="replace")
        log = r.stdout + r.stderr
        logfile = os.path.join(workdir, base + ".log")
        if os.path.exists(logfile):
            log = open(logfile, encoding="utf-8", errors="replace").read()
        if "Output written" in log:
            ok = True
            print("OK on pass %d" % n)
            break
        print("retry %d (no output yet)" % n)

    errs = len(re.findall(r"(?m)^! ", log))
    miss = log.count("Missing character")
    # count placeholder marker text — adapt if you changed \figincl's wording
    ph = log.count("[figure:") + log.count("рисунок:") + log.count("[рисунок")
    m = re.search(r"Output written on \S+ \((\d+) pages", log)
    pages = m.group(1) if m else "?"

    print("pages=%s  errors=%d  missing-char=%d  placeholders=%d  %s"
          % (pages, errs, miss, ph, "BUILT" if ok else "FAILED"))
    if errs:
        for line in re.findall(r"(?m)^! .*", log)[:8]:
            print("   ", line)
    sys.exit(0 if ok and errs == 0 else 1)


if __name__ == "__main__":
    main()
