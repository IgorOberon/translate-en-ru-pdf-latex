#!/usr/bin/env bash
# Compile the assembled document with XeLaTeX.
# Usage: build.sh <build_dir>
set -euo pipefail

BUILD="${1:?usage: build.sh <build_dir>}"
cd "$BUILD"

echo ">> latexmk -xelatex main.tex"
# nonstopmode so a single error doesn't hang; inspect main.log on failure.
if latexmk -xelatex -interaction=nonstopmode -file-line-error main.tex; then
  echo ">> Built: $BUILD/main.pdf"
else
  echo ""
  echo "!! Compilation reported errors. Open main.log and grep for lines like 'main.tex:NN:'."
  echo "   Most common cause: an unescaped special character in translated prose."
  echo "   Escape:  % -> \\%   & -> \\&   _ -> \\_   # -> \\#   \$ -> \\\$   { -> \\{   } -> \\}"
  exit 1
fi
