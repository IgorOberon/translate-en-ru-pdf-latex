# Figure fix patterns

Concrete, repeatable fixes for the problems found while inspecting renders. Apply
the **minimal** change that resolves the issue, then re-render to confirm. Each
fix below is keyed to a symptom you see in the PNG.

## Title / heading overlaps a box or the content

Symptom: a bold title node sits on top of a formula box, panel header, or the top
row of a diagram.

Fix: move the title to a clear band **above everything**. Find the topmost content
y-coordinate and place the title above it with a gap. If the title was placed
mid-figure (e.g. `at (x, 1.7)` inside a matrix that spans y∈[0,2]), that's the
bug — raise it (`at (x, 3.3)`). If the title duplicates text already in a box
(e.g. both say "Orthogonal matrix Q:"), shorten the title so they don't compete.

## Two labels / a caption box collide with content above

Symptom: a bottom legend or "summary" box rides up into the brackets/labels above
it; or panel sub-labels sit at the same height as a wide box.

Fix: push the box further down (increase the gap), **or** move the small labels to
a free corner (e.g. panel titles into the top-left of each panel instead of the
crowded bottom). Verify the new gap in the render.

## Arrow label duplicates a box and collides

Symptom: an arrow is labelled with the full formula that the central box already
states, and the two overlap.

Fix: label the arrow with the short symbol only (e.g. `A^+`) and let the box carry
the full formula. Removes both the duplication and the collision.

## Faint / invisible fills and strokes ("too transparent")

Symptom: a region or marker is barely visible.

Fix: raise the saturation. Typical bumps that read well on screen and in print:

| was | use |
|-----|-----|
| `fill=X!3` / `X!5` | `fill=X!12` |
| `fill=X!8` / `X!10` | `fill=X!12`–`X!15` |
| dashed `X!30`/`!40` | `X!55`–`X!65` |
| `opacity=0.5` (dots/marks) | `opacity=0.7` |
| thin box border | add `line width=0.6pt` |

Add `draw=X!50` borders to filled boxes so they read as distinct objects.

## A label is hard to read over lines/fills

Fix: give it an opaque background: `node[fill=white, inner sep=1pt] {...}`. Standard
for labels that sit on axes, grids, or translucent regions.

## An element is buried under a filled node, or an arrow lands inside box text

Symptom: an inter-step arrow is drawn at coordinates that fall inside an adjacent
box; or a mark is hidden under a fill.

Fix: this usually means boxes are too close / too wide and overlap each other.
**Spread the boxes apart** (increase their x/y separation or reduce `text width`)
so the connector sits in the gap. Often the buried connector can simply be removed
if the sequence (Step 1/2/3) is already clear.

## Cramped sub-panel with packed labels

Fix: enlarge that panel (bump its local `scale`), and move labels to distinct
edges/angles so they don't stack. A nested "inset" figure often just needs
`scale` raised and one label relocated to a free side.

## Figure too small overall

Fix: raise the `tikzpicture` `scale` (e.g. `scale=1.0` → `1.15`). Note `scale`
enlarges **coordinates**, not font size — which is exactly what's wanted: elements
spread apart (fewer overlaps) and the figure renders larger. Watch that a wide
figure doesn't exceed `\textwidth` after scaling; if it might, wrap the `\input`
in the document with `\resizebox{\textwidth}{!}{...}` or `adjustbox` `max width`.

## Draft leftovers in the render

Symptom: stray glyphs, a debug line, or "TODO"/"VERIFY"/half-finished alt versions
that actually print.

Fix: delete the dead `\draw`/comment/alternative. A `\draw[...] (x,y);` with only
a coordinate and no path operation draws nothing — remove it.

## Scrambled coordinates (a real bug, not just layout)

Symptom: labels are right but in the wrong cells/positions (e.g. column entries
off by one, two identical labels stacked, a header sunk into the body).

Fix: recompute the intended coordinates from the figure's own grid/structure and
correct each misplaced node. These are genuine errors the compiler never reports —
the render is the only way to catch them, so look carefully at data-bearing
diagrams (matrices, tables-as-tikz, wiring diagrams).

## Unicode glyphs in math mode

`°`, `≠`, etc. inside `$...$`: with `xelatex`/`lualatex` + a Unicode text font
these usually render fine (check the render before "fixing"). Only convert to
`^\circ`, `\ne`, etc. if the glyph is actually missing/dropped in the PNG — don't
mass-rewrite working output.
