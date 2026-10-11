#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Guarded find-and-replace helpers for safe project-wide LaTeX typography sweeps.

Two reusable primitives plus ready-made CLI recipes. Import the functions for custom
sweeps, or run a recipe. Always grep-verify (remaining == 0) and build-verify after.

Functions:
  guarded_swap(files, old, new)        -- replace old->new ONLY in files where old
                                          occurs exactly once (no silent over-match)
  regex_sweep(files, pattern, repl,    -- per-line regex; skips %-comment lines by
              skip_comments=True)         default so comments/headers aren't touched

CLI recipes (operate on files passed as args, e.g. a glob expanded by the shell):
  python safe_replace.py dash      FILES...   # literal em-dash  ->  ---
  python safe_replace.py abbrev    FILES...   # т.е./т.д./т.к./т.п.  ->  thin-space form
  python safe_replace.py nbsp-ref  FILES...   # "word \cref{}" -> "word~\cref{}" (refs only)
"""
import io, os, re, sys

if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')


def guarded_swap(files, old, new):
    total = 0
    for f in files:
        t = open(f, encoding='utf-8').read()
        c = t.count(old)
        if c != 1:
            print(f'SKIP ({c}x) {f}: {old[:50]!r}')
            continue
        open(f, 'w', encoding='utf-8').write(t.replace(old, new))
        print(f'OK  {f}')
        total += 1
    print(f'--- swapped in {total}/{len(files)} files ---')
    return total


def regex_sweep(files, pattern, repl, skip_comments=True):
    pat = re.compile(pattern)
    total = 0
    for f in files:
        lines = open(f, encoding='utf-8').read().split('\n')
        n, out = 0, []
        for ln in lines:
            if skip_comments and ln.lstrip().startswith('%'):
                out.append(ln); continue
            new, k = pat.subn(repl, ln)
            n += k; out.append(new)
        if n:
            open(f, 'w', encoding='utf-8').write('\n'.join(out))
            print(f'{os.path.basename(f)}: {n}')
            total += n
    print(f'TOTAL: {total}')
    return total


# ---- recipes -------------------------------------------------------------------

def recipe_dash(files):
    """Literal em-dash (U+2014) -> '---'. SAFETY: caller must first confirm there are
    no digit-em-dash-digit ranges and no glued (no-space) em-dashes:
        grep -roE '[0-9]—[0-9]'   and   grep -roE '[^[:space:]]—[^[:space:]]'
    If glued ones exist, this also spaces them ('word—word' -> 'word --- word')."""
    DASH = '—'
    total = 0
    for f in files:
        t = open(f, encoding='utf-8').read()
        if DASH not in t:
            continue
        n = t.count(DASH)
        t = re.sub(r'(\S)' + DASH + r'(\S)', r'\1 --- \2', t)  # glued -> spaced
        t = t.replace(DASH, '---')
        open(f, 'w', encoding='utf-8').write(t)
        print(f'{os.path.basename(f)}: {n}'); total += n
    print(f'TOTAL em-dashes: {total}')


def recipe_abbrev(files):
    """Russian abbreviations т.е./т.д./т.к./т.п. (bare or with '~') -> thin-space form
    'т.\\,е.' etc. Idempotent (won't match already-correct 'т.\\,е.')."""
    pat = r'т\.(~?)([едкп])\.'
    regex_sweep(files, pat, lambda m: 'т.\\,' + m.group(2) + '.', skip_comments=False)


def recipe_nbsp_ref(files):
    """Insert a non-breaking space before cross-references: 'word \\cref{' -> 'word~\\cref{'.
    Refs only (NOT \\cite, which lives in citation lists). Requires a non-space, non-tilde
    char before the space, so indentation and 'range--\\cref' are untouched."""
    pat = r'([^\s~%])[ ](\\(?:cref|Cref|ref|eqref|autoref|pageref)\{)'
    regex_sweep(files, pat, lambda m: m.group(1) + '~' + m.group(2))


if __name__ == '__main__':
    if len(sys.argv) < 3:
        print(__doc__); sys.exit(1)
    cmd, files = sys.argv[1], sys.argv[2:]
    {'dash': recipe_dash, 'abbrev': recipe_abbrev, 'nbsp-ref': recipe_nbsp_ref}[cmd](files)
