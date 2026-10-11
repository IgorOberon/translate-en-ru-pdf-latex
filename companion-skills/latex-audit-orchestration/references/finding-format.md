# Finding format

Every reviewer writes findings in this exact shape. Uniformity is what lets the
orchestrator aggregate, de-duplicate, and rank across dozens of findings files.

## Per-finding template

```
### [CRITICAL|MAJOR|MINOR] One-line headline (what's wrong, in a phrase)
- File: <relative/path.tex>, place: <line number / environment / \label>
- Type: math | notation | reference | typo | figure | markup
- What's wrong: <concise explanation; for math, the computed/correct value>
- How to fix: <the concrete change to make>
- Confidence: high | medium | low
```

## Findings-file header

Each `audit/findings/<batch>_<role>.md` starts with:

```
# <batch> — <role>
- Files: <the files reviewed>
- Date: <date>
- Checked: <what was verified, e.g. "balance of $…$ and environments confirmed">
---
```

…then the findings, and a final line:

```
TOTAL: CRITICAL=<n>, MAJOR=<n>, MINOR=<n>
```

## Severity

- **CRITICAL** — mathematically wrong, breaks the build, or actively misleads the
  reader (e.g. a law stated with the wrong inverse, a false numeric answer, a proof
  that's circular). Fix first.
- **MAJOR** — wrong/broken cross-references, notation conflicts, incorrect or
  mislabeled figures, draft text that renders, systematic markup that breaks a build
  mode.
- **MINOR** — typography, language, style, source-consistency nits.

## Confidence

State it honestly. **medium/low** flags things worth a human's judgment (a debatable
convention, a suspected-but-unverified layout issue). **high** is for things you've
confirmed (recomputed a number, found a literal contradiction in the same file).

## What NOT to do

- Don't propose edits the audit will apply — the audit is read-only; findings *describe*
  the fix. Application happens in the fixing stage.
- Don't flag comment-only/verbatim occurrences as reader-facing (note them separately if
  at all).
- Don't pad: a clean file gets a short findings file saying so.
