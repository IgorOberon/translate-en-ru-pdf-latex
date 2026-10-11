#!/usr/bin/env bash
# Extract an English PDF to markdown (math kept as LaTeX) + figures.
# Usage: extract.sh <input.pdf> <output_dir> [auto|digital|scan|math]
#
# Tool CLIs drift between versions — if a command fails, check its --help.
set -euo pipefail

PDF="${1:?usage: extract.sh <input.pdf> <output_dir> [auto|digital|scan|math]}"
OUT="${2:?output dir required}"
MODE="${3:-auto}"

mkdir -p "$OUT"
name="$(basename "${PDF%.*}")"

echo ">> Extracting '$PDF' (mode: $MODE) -> $OUT"

case "$MODE" in
  digital)
    # Born-digital PDFs, little/no math: fast, no GPU, no OCR.
    #   pip install pymupdf4llm
    python - "$PDF" "$OUT/$name/$name.md" <<'PY'
import os, sys, pymupdf4llm
pdf, out = sys.argv[1], sys.argv[2]
os.makedirs(os.path.dirname(out), exist_ok=True)
open(out, "w", encoding="utf-8").write(pymupdf4llm.to_markdown(pdf))
print("wrote", out)
PY
    ;;
  math)
    # Formula-dense documents: MinerU has the best formula fidelity.
    #   pip install mineru
    mineru -p "$PDF" -o "$OUT" || {
      echo "!! MinerU failed. Install it (pip install mineru), or fall back to:"
      echo "   $0 \"$PDF\" \"$OUT\" auto"
      exit 1
    }
    ;;
  scan)
    # Scanned books: Marker with forced OCR (pdf-craft is a book-specific alternative).
    marker_single "$PDF" --output_dir "$OUT" --output_format markdown --force_ocr
    ;;
  auto|*)
    # Good general default: Marker — fast, keeps inline math as LaTeX, extracts images.
    #   pip install marker-pdf
    #   add --use_llm for messy layouts, --force_ocr for scans.
    marker_single "$PDF" --output_dir "$OUT" --output_format markdown
    ;;
esac

echo ">> Done. Look for the .md and image files under: $OUT/$name/"
echo ">> Next: python scripts/mask_math.py mask <that .md> work/book.masked.md work/book.map.json"
