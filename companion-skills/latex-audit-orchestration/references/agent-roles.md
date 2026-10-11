# Reviewer role briefs

Paste the relevant brief into each subagent's prompt (or register as a custom agent).
Each subagent receives: this brief + its exact file list + `finding-format.md` + the
path to write its findings (`audit/findings/<batch>_<role>.md`) + the shared canon
references (the project's macros / notation / conventions files). It reads **only**
those — not the whole repo — and returns a 3–5 line summary (counts by severity +
headline issues), with the detail written to its findings file.

All reviewers work **read-only** and use the finding format. Reviews are in the
document's own language.

---

## math-reviewer — mathematical correctness

Check definitions, theorem statements, proofs, derivations, and worked numeric
examples. Flag: false statements, gaps/circularity in proofs, wrong hypotheses,
sign/index errors, and **numeric results that don't check out**.

Key discipline: **recompute numbers, don't eyeball them.** For any concrete
computation (a determinant, an SVD, a least-squares solution, an eigenvector), run a
quick `numpy`/`sympy` check and compare. Many "looks plausible" answers are wrong by a
sign, a factor, or a stale value left from an earlier draft. Verify before flagging,
and state the computed value in the finding.

Also watch for concepts used before they're introduced (a forward dependency the text
doesn't acknowledge) and "bridge" claims that misattribute a result to the wrong
chapter.

## consistency-checker — cross-document coherence

Check that notation, terminology, numbering, and cross-references are coherent **across
all files**, against the project's stated canon (macros/notation/conventions docs).
Flag: a symbol with two meanings or two symbols for one concept; a term defined two
ways; `\ref`/`\cref` that resolve wrong or point across files that won't resolve in the
target build mode; transition/transform conventions stated in opposite directions in
different chapters; dead/unused macros; duplicated labels.

Produce, alongside findings, raw material for the notation table: concept → every
variant seen (with locations) → which is dominant.

## proofreader — language, typography, markup

Check the prose and the LaTeX markup. Flag: spelling/grammar/agreement/punctuation
errors; mixed-script words (Latin letters inside a native-script word from autocorrect);
straight quotes where guillemets/curly are wanted; dash style; missing non-breaking
spaces before refs/after abbreviations; **draft leftovers that render** ("TODO",
"VERIFY", "wait, no", half-finished alternative passages, stray ellipses); environment/
brace/`$` balance; `\section` titles with raw Unicode that pollutes PDF bookmarks.

Distinguish rendered text from comments/verbatim — a defect only matters if it reaches
the PDF (note the difference; don't flag comment-only occurrences as reader-facing).

## figure-auditor — figures (TikZ/PGF/plots)

For each figure check: **mathematical correctness** (does it depict the right object?
do coordinates/labels match the claim?), readability (overlaps, contrast, size),
agreement with the surrounding text and caption, and style consistency. Flag figures
that are duplicates, mislabeled, or contradict their caption.

Note: layout problems (overlaps, faint fills) are best confirmed by *rendering* the
figure — pair this role with the `latex-figure-review` skill in the fixing stage. In
the audit, flag suspected layout issues plus any correctness/labelling errors found
from the source.
