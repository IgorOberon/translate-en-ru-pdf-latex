# Aggregation document templates

After all findings files exist, read them and produce these four reports in `audit/`.
De-duplicate (same issue from two roles → one entry) and promote anything recurring in
many places to a "systemic" entry.

---

## `audit/ERRORS.md` — actionable checklist

Grouped by severity, then by chapter. Every item is a checkbox with a precise location,
so it drives the fixing stage directly.

```markdown
# Errors

## CRITICAL
- [ ] L05 `thm:covector_coords` (lectures/L05.tex:308) — law stated with S^{-1};
      proof and summary use S. Fix: S^{-1} → S. [math, high]
- [ ] ...

## MAJOR
- [ ] ...

## MINOR
- [ ] ...
```

## `audit/NOTATION.md` — the notation table

The cross-cutting view that surfaces systemic conflicts. One row per concept.

```markdown
| # | Concept | Canonical (proposed) | Variants seen (locations) | Where | Action |
|---|---------|----------------------|---------------------------|-------|--------|
| 1 | transpose | `\T` (= ^{\top}) | `^\top`, `^{\mathsf T}`, `\T` | many | unify to \T |
| 2 | transition matrix | "from e to e'" (cols = e' in e) | L05 "e→e'", L06 "e'→e" (same matrix!) | L05/L06 | unify wording |
| 3 | image | `\Img` vs `\im` | … | … | pick dominant; update canon |
```

## `audit/IMAGES_PLAN.md` — figures

Every figure with its issues + a shared style guide (palette, line weights, arrow
style, label conventions, right-angle marker). The fixing stage uses
`latex-figure-review` against this.

```markdown
## Style guide
- Palette: blue/red/green 60–80% black; faint fills ≥ X!12; arrows >=Stealth; ...

## Per-figure
| Figure | Issue | Severity | Fix |
|--------|-------|----------|-----|
| L08_F6 | Σ-box overlaps title | MAJOR | raise title above box |
| ...    | ...   | ...      | ... |
```

## `audit/SUMMARY.md` — one page (output to the user)

```markdown
# Audit summary
- Files reviewed: N   Findings: CRITICAL=a, MAJOR=b, MINOR=c
## Top 10 issues
1. ...
## Systemic problems
- <conflicts that appear across many files — the notation clashes, a recurring
  draft-artifact pattern, a build-mode bug class>
## Recommendation
- Suggested fixing order (CRITICAL math → MAJOR refs/notation/figures → typography),
  and a request: "Shall I start the fixing stage?"
```

Output `SUMMARY.md` in chat and ask whether to begin fixing. Keep `audit/progress.md`
current so the whole pipeline is resumable.
