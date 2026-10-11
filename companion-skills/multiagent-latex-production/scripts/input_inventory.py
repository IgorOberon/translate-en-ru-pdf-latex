#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Inventory \\input/\\include and \\label across an assembled LaTeX project.

Usage:
    input_inventory.py main.tex

Walks the include tree starting at the master file and reports the two join-time
defects a fanned-out build creates:

  1. A file pulled in more than once  -> its \\label runs twice
                                         -> "multiply defined" at build time.
  2. A \\label{...} string defined in two different files -> same symptom from a
     copy/paste rather than a double \\input.

It resolves \\input{f} / \\include{f} relative to the MASTER file's directory
(LaTeX resolves include paths against the main job directory, not against the
file that contains the \\input — so a nested chapters/chNN.tex that says
\\input{chapters/chNN/sec.tex} still means <root>/chapters/chNN/sec.tex), adding
a ".tex" extension when missing. It does not compile; run it after a wave merges
into the master, then fix before building.

Pure standard library; no LaTeX or PyMuPDF needed.
"""
import os
import re
import sys

INPUT_RE = re.compile(r"\\(?:input|include)\s*\{([^}]+)\}")
LABEL_RE = re.compile(r"\\label\s*\{([^}]+)\}")


def resolve(name, root_dir):
    p = name.strip()
    if not os.path.splitext(p)[1]:
        p += ".tex"
    return os.path.normpath(os.path.join(root_dir, p))


def walk(master):
    """Return (include_counts, label_locations) over the whole tree.

    All \\input/\\include paths resolve against root_dir = the master's own
    directory (LaTeX's main job directory), constant through the whole walk.
    """
    root_dir = os.path.dirname(os.path.abspath(master))
    include_counts = {}            # path -> times \input/\include'd
    label_locations = {}           # label string -> [files it appears in]
    seen = set()                   # files whose body we've already scanned
    stack = [os.path.normpath(master)]
    while stack:
        f = stack.pop()
        if f in seen or not os.path.exists(f):
            if not os.path.exists(f):
                print("  (warning: included file not found: %s)" % f)
            continue
        seen.add(f)
        text = open(f, encoding="utf-8", errors="replace").read()
        for m in INPUT_RE.finditer(text):
            child = resolve(m.group(1), root_dir)
            include_counts[child] = include_counts.get(child, 0) + 1
            stack.append(child)
        for m in LABEL_RE.finditer(text):
            label_locations.setdefault(m.group(1), []).append(f)
    return include_counts, label_locations


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(2)
    master = sys.argv[1]
    include_counts, label_locations = walk(master)

    dup_inc = {p: n for p, n in include_counts.items() if n > 1}
    dup_lbl = {l: fs for l, fs in label_locations.items() if len(set(fs)) > 1}

    print("files included: %d   labels defined: %d"
          % (len(include_counts), len(label_locations)))

    if dup_inc:
        print("\n!! files \\input/\\include'd more than once "
              "(remove the extra include):")
        for p, n in sorted(dup_inc.items()):
            print("   %dx  %s" % (n, p))
    else:
        print("\nok: no file included more than once")

    if dup_lbl:
        print("\n!! \\label defined in more than one file "
              "(rename or delete the duplicate):")
        for l, fs in sorted(dup_lbl.items()):
            print("   %s" % l)
            for f in sorted(set(fs)):
                print("        %s" % f)
    else:
        print("ok: no label defined in two files")

    sys.exit(0 if not dup_inc and not dup_lbl else 1)


if __name__ == "__main__":
    main()
