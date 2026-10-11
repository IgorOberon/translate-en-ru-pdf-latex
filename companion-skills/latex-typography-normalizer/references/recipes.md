# Normalization recipes

Each recipe: the **pre-check** (what to confirm before touching anything), the
**replacement** (with its guard), and the **post-check**. `scripts/safe_replace.py`
implements the common ones; the regexes are written out here so you can adapt them.

> Throughout: prefer normalizing the **minority** form to the **majority** form
> (count both first), and build-verify after.

---

## Em-dash: literal `—` (U+2014) ↔ `---`

- **Direction:** count `grep -roF -- '---' | wc -l` vs `grep -roF '—' | wc -l`; go to
  the majority (in practice `---` usually dominates).
- **Pre-check (this is what makes it safe):**
  - `grep -roE '[0-9]—[0-9]'` → expect 0 (a number *range* should be an en-dash `–`,
    not a spaced em-dash; if present, handle separately).
  - `grep -roE '[^[:space:]]—[^[:space:]]'` → glued dashes (no surrounding spaces). If
    present, the recipe will also add spaces (`word—word` → `word --- word`), which is
    correct for Russian/English sentence dashes.
- **Replace:** `safe_replace.py dash FILES...` (literal `—` → `---`).
- **Post-check:** `grep -roF '—'` → 0. Build → 0 errors (render is identical, so any
  error means a bad-context hit).

## Straight quotes `"…"` → guillemets/curly

- **Pre-check is essential** — most stray `"` in a LaTeX repo are NOT prose quotes:
  they're in **comments**, `\verb`/listings, or **code** (pgfmath `? "a" : "b"`, package
  options). Inspect every match: `grep -rn '"' --include=*.tex`. Only convert genuine
  rendered prose quotes. Often the conclusion is "nothing to do".
- **Replace** (only the confirmed prose ones, individually): `"text"` → `«text»` (ru) or
  ``` ``text'' ``` (en). Don't run a blind `"([^"]+)"`→ sweep over a repo with code.

## Russian abbreviations `т.е.`/`т.д.`/`т.к.`/`т.п.` → thin-space form

- **Target:** `т.\,е.` (thin non-breaking space inside the abbreviation).
- **Replace:** `safe_replace.py abbrev FILES...`. Regex `т\.(~?)([едкп])\.` →
  `т.\,\2.` — matches bare `т.е.` and `т.~е.`, **idempotent** (won't re-match an
  already-correct `т.\,е.` because `\,` isn't `~`/letter).

## Non-breaking space before cross-references

- **Target:** `слово~\cref{…}` / `word~\ref{…}` so the reference number can't orphan to
  a line start.
- **Replace (refs only, NOT `\cite`):** `safe_replace.py nbsp-ref FILES...`. Regex
  `([^\s~%])[ ](\\(?:cref|Cref|ref|eqref|autoref|pageref)\{)` → `\1~\2`. The leading
  non-space/non-tilde/non-`%` guard means: line-start indentation is untouched, an
  existing `~` isn't doubled, ranges like `--\cref` are skipped, and comment text is
  left alone. **Exclude `\cite`** — citations live in `;`-separated lists / `\sourcetag`
  where `~` is noise.
- "см. L05" / "рис. 3" prose refs: usually only a handful; fix individually
  (`см.~L05`). Most appear in source comments — leave those.

## Macro unification (transpose, condition number, image operator, …)

- **Direction:** count both spellings; normalize the minority. E.g. `^{\top}`/`^\top`
  → a `\T` macro if `\T` dominates; or `\cond` → `\kappa`; or `\im` ↔ `\Img`.
- **Replace:** guarded sweep, protecting the macro you're keeping by name (don't turn
  `\condK` into `\kappaK`). A `safe_replace.regex_sweep` with an anchored pattern, or
  exact-once `guarded_swap` per call-site for small counts.
- **CRITICAL post-check — no `\macroLETTER`:** after the sweep, run
  `grep -rnE '\\<macro>[A-Za-z]'` (e.g. `\\T[A-Za-z]`). A hit like `E\TE` is an
  **undefined control sequence** (`\TE`) created when the old form had no trailing
  space (`E^{\top}E`). Fix by inserting a space (`E\T E` — math mode ignores it, render
  unchanged). **Exclude** legitimate longer control words (`\Theta`, `\TeX`, `\Top`…)
  from the fix. This single check catches the one class of error a macro sweep
  introduces — don't skip it.
- Update the project's canon/notation doc to state the chosen form, so the convention
  is recorded and future drift is catchable.

## Mixed-script words (Latin letters inside a Cyrillic word, or vice-versa)

- Auto-correct/typos leave things like `кosos` (Latin o,s,o in `кососимметричность`):
  compiles, but breaks text search and renders as mixed-alphabet. Find with
  `grep -rnE '[а-яёА-ЯЁ][a-zA-Z]|[a-zA-Z][а-яёА-ЯЁ]'`; fix each (watch for false
  positives like a `% kappa` comment).
