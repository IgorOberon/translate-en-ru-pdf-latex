#!/usr/bin/env bash
# Convert translated markdown into a full LaTeX document using the Russian preamble.
# Usage: to_latex.sh <translated.md> <build_dir> [preamble.tex]
set -euo pipefail

MD="${1:?usage: to_latex.sh <translated.md> <build_dir> [preamble.tex]}"
BUILD="${2:?build dir required}"
PREAMBLE="${3:-assets/preamble.tex}"

mkdir -p "$BUILD"

echo ">> pandoc: markdown -> LaTeX body fragment"
ASSETS="$(cd "$(dirname "$0")/.." && pwd)/assets"
pandoc "$MD" \
  --from=markdown+raw_tex+tex_math_dollars \
  --to=latex \
  --top-level-division=chapter \
  --wrap=preserve \
  --lua-filter="$ASSETS/figcaption.lua" \
  --lua-filter="$ASSETS/structure.lua" \
  --output="$BUILD/body.tex"

echo ">> assembling $BUILD/main.tex"
{
  cat "$PREAMBLE"
  echo ""
  echo "\\begin{document}"
  echo "\\tableofcontents\\clearpage"
  echo "\\input{body.tex}"
  echo "\\end{document}"
} > "$BUILD/main.tex"

# Bring extracted figures next to main.tex if an images folder sits by the markdown.
srcdir="$(dirname "$MD")"
for d in "$srcdir/images" "$srcdir"/*_images "$srcdir"/*.md_images; do
  if [ -d "$d" ]; then
    cp -r "$d" "$BUILD/images" 2>/dev/null || true
  fi
done

echo ">> Wrote $BUILD/main.tex   (next: bash scripts/build.sh $BUILD)"
