# Pitfalls that cost hours (with the cheap fix for each)

## 1. Non-Latin text inside math mode → a flood of "Missing character"
Math fonts (even `STIX Two Math`) carry no Cyrillic/Greek-prose/CJK glyphs. The
moment target-language prose lands inside `\begin{equation}…\end{equation}` or
`$…$`, every such letter is dropped and the log fills with
`Missing character: There is no … in font …`.

- **Real formulas** stay in math mode (Latin/Greek letters, operators — fine).
- **Numbered *textual* results** (a sentence that happens to have a number) go in
  a **text box**, never an equation:
  ```latex
  \begin{axiombox}
  <target-language sentence with inline $math$>.\hfill(N)
  \end{axiombox}
  ```
- Inline target-language words that must sit inside a formula → wrap in
  `\text{…}` (amsmath), which switches back to the text font.

## 2. "Fixing" structure with a greedy/lazy regex corrupts the whole file
A `re.sub(r"\\begin\{equation\}(.*?)\\tag\{32\}…", …, t, flags=re.S)` looks
innocent. But `.*?` is lazy from the **first** `\begin{equation}` in the file, so
it spans **everything** up to that far-away `\tag{32}` — wrapping dozens of
unrelated equations into one box and shredding the document. Applying eight such
subs in a row compounds the damage.

- Never run DOTALL `.*?` across `\begin…\end` spans on a whole file.
- To repair `\begin/\end{equation|axiombox|…}` mismatches, use
  `scripts/fix_env_pairing.py`: it **stack-pairs** ends to begins and sets each
  begin's environment to its end's. It trusts the `\end` + `\tag/\hfill` (which
  encode intent) and rebuilds the begins. Handles nesting; reports true
  unbalance it can't guess.
- Prefer targeted, anchored edits (exact `old_string`) over clever global regex.

## 3. Transient "memory exhausted" on an otherwise-fine build
LuaTeX loads babel/hyphenation into one process and can OOM under system RAM
pressure — then succeed on a re-run. Don't debug a phantom: build through
`scripts/compile_retry.py` (retries, stops on `Output written`). If it persists,
free RAM (close other apps) rather than editing the document.

## 4. A chapter won't compile because its figures aren't extracted yet
Write the translation first, extract figures later. The `\figincl` in the
preamble template **degrades to a labelled placeholder** when the PNG is absent,
so the chapter compiles throughout. `compile_retry.py` reports how many
placeholders remain — drive that to 0 before calling a chapter done.

## 5. Figure numbers in captions disagree with `\figref`
If the source numbers figures **per chapter** (`[1],[2]…`) set
`\renewcommand{\thefigure}{\arabic{figure}}`; if **globally** (`[3.5]`) keep
`\thechapter.\arabic{figure}`. The caption label format (`[#2]`) renders
`\thefigure`, and your `\figref{N}` prints `[N]` — make the two schemes match or
captions say `[1.5]` while the text says `[5]`. (Book class resets the `figure`
counter at each `\chapter` regardless, so per-chapter numbering still restarts.)

## Bonus: verify by looking, not by exit code
`0 errors` does **not** mean the page is right. A figure crop can include the page
header or caption; a wrapfigure can overlap text; a montage panel can be clipped.
Render the new pages, montage the new figures, and **read the images**. The
extract-pdf-figures and latex-figure-review skills are this loop.
