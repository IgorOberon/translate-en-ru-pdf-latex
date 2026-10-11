---
name: latex-typography-normalizer
description: >-
  Safely apply project-wide typography and notation normalizations across a large
  LaTeX codebase: unify em-dashes (literal "—" vs "---"), straight quotes vs guillemets/
  curly quotes, non-breaking spaces before \ref/\cref/\cite and after abbreviations
  (e.g. Russian "т.е."→"т.\,е."), and unify duplicated macros (e.g. ^\top vs a \T
  macro, \cond vs \kappa, \im vs \Img). Use whenever a user asks to "unify/normalize
  notation", "fix the dashes/quotes/spacing consistently", "make the typography
  consistent", "standardize how we write transpose/the condition number/etc." across
  many files. The point of this skill is the DISCIPLINE that makes a 900-replacement
  sweep safe: measure scope with grep first, replace with guards (count/uniqueness
  checks, protected contexts), verify zero remaining, and build-verify after — never
  a blind sed across the repo.
---

# LaTeX typography & notation normalizer

## Why this exists

Mass find-and-replace across a LaTeX project is high-leverage but dangerous: a blind
`sed` can mangle math, hit comments/verbatim, or change a macro that has hundreds of
valid call-sites. This skill is the **safe procedure** for it. The replacements are
easy; the *discipline* is the value.

## The discipline (do this for every normalization)

1. **Decide the target form, and the direction by majority.** When two forms coexist,
   normalize the minority to the majority (fewer edits, less risk) unless a convention
   says otherwise. Count both: `grep -roF -- '---' | wc -l` vs the count of `—`.
2. **Measure scope and inspect contexts** before changing anything. `grep` the pattern
   and read a sample. Confirm the matches are all the thing you think they are — watch
   for the pattern appearing in **comments** (`%…`), **verbatim/listings**, **code
   strings** (e.g. a pgfmath `? "blue!25" : "gray!8"` is not a text quote), **math mode**,
   and **ranges** (a `5–7` en-dash range must not become a spaced em-dash).
3. **Replace with guards, not blindly:**
   - Per-occurrence text fixes: require the `old` string to occur **exactly once** per
     file (count check) so you never silently hit an unintended match.
   - Regex sweeps: anchor to exclude the dangerous contexts (skip comment lines; require
     a non-space neighbour so you don't touch indentation or ranges; protect a sibling
     macro by name).
   - Prefer a small Python script over `sed`: it does UTF-8 cleanly, can skip comment
     lines, and can print a per-file count.
4. **Verify zero remaining.** Re-grep for the old form; expect 0 (or only the known-safe
   leftovers, e.g. matches inside comments you chose not to touch).
5. **Build-verify.** Recompile (master and/or the touched standalone files); confirm
   **0 errors**. A glyph swap like `—`→`---` is render-identical, so any new compile
   error means the sweep hit a context it shouldn't have.

`scripts/safe_replace.py` implements the guarded-replace pattern (exact-once string
swaps + line-skipping regex). `references/recipes.md` has tested recipes for the
common normalizations with their exact guards.

## What "safe" looks like — a worked example

Unifying 940 literal em-dashes to `---`:
- `grep -roF '—' | wc` → 940; `grep -roF -- '---' | wc` → 6001 ⇒ normalize `—`→`---`.
- Check `[0-9]—[0-9]` (ranges) → 0, and `\S—\S` (glued, no spaces) → 0 ⇒ pure spaced
  text dashes ⇒ a literal glyph swap is safe.
- Script replaces `—`→`---` everywhere; re-grep `—` → 0; master build → 0 errors.

The check *before* the swap (no ranges, no glued, no math) is what makes it safe — not
the swap itself.

## Macro unification (transpose, condition number, image, …)

Same discipline, plus two extra cautions:
- **Don't create `\macroLETTER`.** Replacing `^{\top}`→`\T` inside `E^{\top}E` yields
  `E\TE`, and `\TE` is an *undefined control sequence* (compile error). After any macro
  sweep, `grep` for `\<macro>[A-Za-z]` and fix (insert a space: `E\T E` — math mode
  ignores it, render is identical) — but exclude legitimate longer control words
  (`\Theta`, `\TeX`).
- **Pick the side that's already dominant** and update the canon/notation doc to match,
  rather than forcing 241 correct sites to change for 11. If a macro is genuinely
  one-argument and 11 call-sites wrongly use two, fix the 11.

## Scope of files

Sweep the content directories (lectures, problems, solutions, handouts, cheatsheets,
faq, pre/postlecture, plans) **and** root-level index docs. Comments are usually safe
to leave or change (render-irrelevant); be explicit about which you did.

## Report

State each normalization, the count changed, the direction and why, the guards used,
the "remaining = 0" check, and the post-build result.
