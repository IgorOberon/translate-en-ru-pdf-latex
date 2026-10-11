# Common standalone-build bugs and their fixes

Each entry: the error, why it happens, and a verified before→after. These recur
across course/book repos because the same templates get copied between files.

---

## 1. `Option clash for package geometry`

**Why:** the project preamble already does `\usepackage[..]{geometry}`. A file then
re-loads it with different options (often to go `landscape` for a cheatsheet). A
package may only be loaded with options **once**.

**Fix:** use `\geometry{..}` to *set* options on the already-loaded package — and
put it **after** `\input{preamble}` (so geometry is defined when you call it). To
override the preamble's portrait `a4paper`, name the orientation explicitly.

```latex
% before  (after \input{../preamble})
\usepackage[margin=1.2cm]{geometry}        % clash
% after
\geometry{landscape,margin=1.2cm}
```

If the file had the load *before* the preamble, moving the line is the real fix:
```latex
% before
\geometry{landscape,margin=1.2cm}   % <-- \geometry not defined yet
\input{../preamble}
% after
\input{../preamble}
\geometry{landscape,margin=1.2cm}
```
Watch for a doubled option (`landscape,landscape`) if a blunt regex prepended one.

---

## 2. `Package biblatex Error: '\bibliographystyle' invalid for 'biblatex'`

**Why:** the preamble loads `biblatex` (`\addbibresource{..}`), but the file ends
with the legacy BibTeX pair. biblatex forbids them.

**Fix:**
```latex
% before
\bibliographystyle{plain}
\bibliography{../references}
% after
\printbibliography
```
These usually sit inside an `\ifnum\incourse=0 … \fi` standalone wrapper, so they
only break standalone builds. Search the whole project — a batch of files authored
from one old template tend to share it (`grep -l '\bibliographystyle'`).

---

## 3. `LaTeX Error: Can be used only in preamble`

**Why:** an aggregator (`\def\incourse{1}` then `\input{handouts/X}`) pulls in a
file whose `\documentclass`/`\usepackage`/`\begin{document}` are **not** guarded, so
they execute inside the aggregator's body.

**Fix:** give the included file the same guard the lectures use, so it's both
standalone and includable:
```latex
\providecommand{\incourse}{0}
\ifnum\incourse=0
  \documentclass[10pt,a4paper]{article}
  \input{../preamble}
  \input{../macros}
  \begin{document}
  \title{...}\maketitle           % everything preamble/title-ish goes inside
\fi

... body (shown in BOTH modes) ...

\ifnum\incourse=0
\end{document}
\fi
```
`\providecommand` is key: standalone ⇒ undefined ⇒ set to 0 ⇒ guard active;
aggregated ⇒ already 1 ⇒ `\providecommand` is a no-op ⇒ preamble skipped. The
guard around `\end{document}` is essential — otherwise the first included file ends
the whole aggregator.

A script that does this across many files: insert the guard-open before the first
`\documentclass`, a `\fi` after the `\maketitle` line, and wrap `\end{document}`.
Verify each file still builds standalone AND the aggregator builds clean.

---

## 4. `LaTeX Error: Not in outer par mode`

**Why:** a float or `\marginpar` (or `\section`) is invoked where LaTeX can't place
it — inside a `tabular` cell, an `\mbox`, a `minipage`, or math mode. Common when a
notation table tries to *demonstrate* a margin-note macro by calling it in a cell:
```latex
$\riskflag{k}$ & \verb|\riskflag{k}| & ...     % \riskflag = \marginpar{...}  -> error
```

**Fix:** show a static *representation* of what the macro produces instead of
invoking it:
```latex
\fbox{\scriptsize\textcolor{red!70!black}{\texttt{R}$k$}} & \verb|\riskflag{k}| & ...
```
General rule: never invoke a `\marginpar`/`\begin{figure}`/`\section` from inside a
box or table cell. Move it out, or render a stand-in.

---

## 5. `File ended while scanning use of \@newl@bel` (and similar `.aux` corruption)

**Why:** a previous compile was interrupted mid-write, leaving a truncated
`\newlabel{...}` in the `.aux`. The next run chokes reading it.

**Fix:** delete the `.aux` (and any `.toc`/`.out`) and recompile (two passes if the
doc uses cross-references):
```bash
rm -f FILE.aux build/FILE.aux
xelatex -interaction=nonstopmode FILE.tex   # pass 1
xelatex -interaction=nonstopmode FILE.tex   # pass 2 (resolve labels)
```
This is transient, not a source bug — but always re-run twice and confirm 0 errors
in the **second** pass, because pass 1 may legitimately report undefined references
that pass 2 resolves.

---

## Triage tip

Before compiling everything, you can pre-find classes 1–3 cheaply:
```bash
grep -rl '\usepackage\[.*\]{geometry}' <dirs>     # class 1 candidates
grep -rl '\bibliographystyle\|\bibliography{'      # class 2 candidates
# class 3: files \input by the aggregator that lack 'incourse'
grep -L incourse handouts/*.tex
```
