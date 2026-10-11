#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Auto-tag a name index (persons) and an optional subject index into the body of
LaTeX chapter files. Stdlib only. Appends \index[REGISTER]{Headword} at the END of
each body paragraph that mentions a canonical name / subject term — never inside a
command, heading, math, or the bibliography. Run AFTER (re)generating the .tex from
source and BEFORE compiling; running twice double-tags, so regenerate first.

Usage:
  py -3 add_index.py TEXDIR NAMES_FILE [SUBJECTS_TSV] [--exclude "Surname1,Surname2"]

NAMES_FILE  : one canonical full name per line, e.g. "Иммануил Кант" or "Кант, Иммануил".
              Lines starting with '#' are ignored. Surname = last whitespace token
              (or the part before a comma). Place names / institutions: omit them
              from this file if you want a people-only "name index".
SUBJECTS_TSV: optional. Each line "REGEX<TAB>HEADWORD". REGEX matches inflected forms
              (e.g. "снят[иеяю]\\w*"). If omitted, no subject index is tagged.
--exclude   : comma-separated surnames to skip (e.g. the book's own subject).

Index register names used: persons, subject. They must be declared in the preamble:
  \\makeindex[name=persons,...]   \\makeindex[name=subject,...]
and entered as \\index[persons]{..} (SQUARE brackets — see check_index_syntax.py).
"""
import sys, re, os, glob, collections

def parse_args(argv):
    pos, exclude = [], set()
    i = 0
    while i < len(argv):
        if argv[i] == "--exclude":
            exclude = {s.strip() for s in argv[i + 1].split(",") if s.strip()}
            i += 2
        else:
            pos.append(argv[i]); i += 1
    if len(pos) < 2:
        sys.exit("usage: add_index.py TEXDIR NAMES_FILE [SUBJECTS_TSV] [--exclude ...]")
    return pos[0], pos[1], (pos[2] if len(pos) > 2 else None), exclude

def load_names(path, exclude):
    """-> dict surname_stem -> 'Surname, Given' headword."""
    names = {}
    for raw in open(path, encoding="utf-8"):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        # markdown table row?  | orig | ru |   -> take the last cell
        if line.startswith("|"):
            cells = [c.strip() for c in line.strip("|").split("|")]
            line = cells[-1] if cells else ""
        line = re.sub(r"\(.*?\)", "", line).strip()
        if not line or not re.search(r"[^\W\d_]", line, re.UNICODE):
            continue
        if "," in line:                      # already "Surname, Given"
            surname = line.split(",", 1)[0].strip()
            head = line
        else:
            toks = line.split()
            surname = toks[-1].strip(".")
            head = surname + (", " + " ".join(toks[:-1]) if len(toks) > 1 else "")
        if not surname or surname in exclude or len(surname) < 4:
            continue
        if not surname[:1].isupper():
            continue
        names.setdefault(surname, head)
    return names

def load_subjects(path):
    subs = []
    if not path:
        return subs
    for raw in open(path, encoding="utf-8"):
        if raw.strip().startswith("#") or "\t" not in raw:
            continue
        body, head = raw.rstrip("\n").split("\t", 1)
        subs.append((re.compile(r"(?<!\w)(?:%s)(?!\w)" % body.strip(), re.I | re.U),
                     head.strip()))
    return subs

def esc(s):
    return s.replace("\\", "\\textbackslash ").replace("{", "\\{").replace("}", "\\}")

def main():
    texdir, names_file, subj_file, exclude = parse_args(sys.argv[1:])
    names = load_names(names_file, exclude)
    subs = load_subjects(subj_file)
    # one alternation for surnames (longest first), capital + up to 3 inflection letters
    pats = sorted(names, key=len, reverse=True)
    NAME_RX = re.compile(r"(?<!\w)(" + "|".join(re.escape(s) for s in pats) +
                         r")\w{0,3}(?!\w)", re.U) if pats else None
    report = collections.Counter()
    files = sorted(glob.glob(os.path.join(texdir, "*.tex")))
    for f in files:
        out, in_bib = [], False
        for ln in open(f, encoding="utf-8").read().split("\n"):
            s = ln.strip()
            if s.startswith(r"\begin{biblist}") or s.startswith(r"\begin{thebibliography}"):
                in_bib = True
            if s.startswith(r"\end{biblist}") or s.startswith(r"\end{thebibliography}"):
                in_bib = False; out.append(ln); continue
            if in_bib or not s or s.startswith("\\"):
                out.append(ln); continue
            found = []
            if NAME_RX:
                for m in NAME_RX.finditer(ln):
                    h = names.get(m.group(1))
                    if h and h not in found:
                        found.append(h)
            subj = [h for rx, h in subs if rx.search(ln)]
            subj = list(dict.fromkeys(subj))
            tags = "".join(r"\index[persons]{%s}" % esc(h) for h in found) \
                 + "".join(r"\index[subject]{%s}" % esc(h) for h in subj)
            if tags:
                ln = ln.rstrip() + tags
                for h in found: report["P:" + h] += 1
                for h in subj:  report["S:" + h] += 1
            out.append(ln)
        open(f, "w", encoding="utf-8").write("\n".join(out))
    npers = sum(v for k, v in report.items() if k.startswith("P:"))
    nsubj = sum(v for k, v in report.items() if k.startswith("S:"))
    print("files:%d  persons:%d marks (%d heads)  subjects:%d marks (%d heads)" % (
        len(files), npers, sum(1 for k in report if k[0] == "P"),
        nsubj, sum(1 for k in report if k[0] == "S")))
    top = report.most_common(12)
    print("top:", ", ".join("%s(%d)" % (k.split(':', 1)[1].split(',')[0], v) for k, v in top))

if __name__ == "__main__":
    main()
