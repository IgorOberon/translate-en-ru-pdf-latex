#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Repair mismatched \\begin/\\end for a set of LaTeX environments by stack-pairing.

Usage:
    fix_env_pairing.py FILE.tex [env1 env2 ...]
    (default envs: equation equation* axiombox)

When does this happen? Almost always after someone "fixes" structure with a
greedy/lazy regex (re.DOTALL `.*?`) that spanned huge ranges and swapped a bunch
of \\begin{equation} <-> \\begin{axiombox} (etc.) while leaving the \\end and the
\\tag/\\hfill in place. The reliable repair is NOT another regex: walk the tokens,
pair each \\end with the nearest open \\begin (a stack), and rewrite each \\begin's
environment to match the environment of the \\end it pairs with. Nested
environments (e.g. an equation* inside an axiombox) are handled correctly.

This only trusts the \\end tokens (and your \\tag/\\hfill content) — so make sure
those encode the intent: a numbered FORMULA ends \\tag{N}\\end{equation}; a
numbered PROSE result ends \\hfill(N)\\end{axiombox}. Then the begins follow.

Prints every change. Idempotent. Reports if the stack is unbalanced (a real
structural bug this can't guess away).
"""
import re
import sys

DEFAULT_ENVS = ["equation*", "equation", "axiombox"]


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    path = sys.argv[1]
    envs = sys.argv[2:] or DEFAULT_ENVS
    # longest first so "equation*" matches before "equation"
    alt = "|".join(re.escape(e) for e in sorted(envs, key=len, reverse=True))
    tok_re = re.compile(r"\\(begin|end)\{(" + alt + r")\}")

    lines = open(path, encoding="utf-8").read().split("\n")

    # collect tokens in document order
    toks = []  # (lineidx, 'b'/'e', env)
    for i, ln in enumerate(lines):
        for m in tok_re.finditer(ln):
            toks.append((i, "b" if m.group(1) == "begin" else "e", m.group(2)))

    fixes = {}          # lineidx -> correct env for a begin
    stack = []
    unbalanced = []
    for (i, be, env) in toks:
        if be == "b":
            stack.append((i, env))
        else:
            if not stack:
                unbalanced.append(("end", i, env))
                continue
            bi, benv = stack.pop()
            if benv != env:
                fixes[bi] = env     # begin must match its paired end
    for (bi, benv) in stack:
        unbalanced.append(("begin", bi, benv))

    for bi, correct in sorted(fixes.items()):
        lines[bi] = tok_re.sub(
            lambda m: "\\begin{%s}" % correct if m.group(1) == "begin" else m.group(0),
            lines[bi], count=1) if "\\begin" in lines[bi] else lines[bi]
        # robust single-swap of the first \begin{...} on that line:
        lines[bi] = re.sub(r"\\begin\{(?:" + alt + r")\}",
                           "\\\\begin{" + correct + "}", lines[bi], count=1)
        print("L%d -> \\begin{%s}" % (bi + 1, correct))

    open(path, "w", encoding="utf-8").write("\n".join(lines))
    print("fixed %d begin(s)." % len(fixes))
    if unbalanced:
        print("WARNING unbalanced (cannot auto-fix):")
        for kind, i, env in unbalanced:
            print("   stray %s{%s} at line %d" % (kind, env, i + 1))


if __name__ == "__main__":
    main()
