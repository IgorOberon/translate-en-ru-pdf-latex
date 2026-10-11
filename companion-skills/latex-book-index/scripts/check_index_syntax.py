#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Assert there are no brace-form named-index bugs in LaTeX sources.

With imakeidx, a named register must be entered as  \index[persons]{Headword}
(SQUARE brackets). The brace form  \index{persons}{Headword}  compiles "successfully"
but routes 'persons' to the default index and TYPESETS '{Headword}' into the body.
This finds every such occurrence so the index isn't silently empty / the body
isn't polluted with stray headwords.

Usage:  py -3 check_index_syntax.py FILE_OR_DIR [REGISTER ...]
        (default registers: persons subject)
Exit code 0 if clean, 1 if any bug found.
"""
import sys, re, os, glob

def files(path):
    if os.path.isdir(path):
        return sorted(glob.glob(os.path.join(path, "**", "*.tex"), recursive=True))
    return [path]

def main():
    args = sys.argv[1:]
    if not args:
        sys.exit("usage: check_index_syntax.py FILE_OR_DIR [REGISTER ...]")
    target = args[0]
    regs = args[1:] or ["persons", "subject"]
    # \index{persons}{...}  — brace form where the first group is a register name
    rx = re.compile(r"\\index\s*\{(" + "|".join(map(re.escape, regs)) + r")\}\s*\{")
    bad = 0
    for f in files(target):
        for i, line in enumerate(open(f, encoding="utf-8"), 1):
            for m in rx.finditer(line):
                bad += 1
                print("%s:%d  BRACE-FORM BUG  \\index{%s}{...}  -> should be \\index[%s]{...}"
                      % (os.path.basename(f), i, m.group(1), m.group(1)))
    if bad:
        print("FAIL: %d brace-form \\index{name}{..} bug(s)" % bad)
        sys.exit(1)
    print("OK: no brace-form named-index bugs")

if __name__ == "__main__":
    main()
