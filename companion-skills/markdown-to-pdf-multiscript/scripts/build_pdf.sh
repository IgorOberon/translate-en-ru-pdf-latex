#!/usr/bin/env bash
# build_pdf.sh — Markdown → печатный PDF (Pandoc + XeLaTeX) для текстов с кириллицей,
# политоническим греческим, немецкими умляутами и латинскими терминами.
# Обобщение сборки семинара по Гегелю и интервью Оселедца: на вход — ЛЮБОЙ список .md.
#
# Использование:
#   ./build_pdf.sh -o "OUT.pdf" -t "Заголовок" [-s "Подзаголовок"] [-a "Автор"] file1.md [file2.md ...]
#
# Каждый входной .md, начинающийся с «# Заголовок», становится главой; «## » — раздел.
# Печатное оглавление — до разделов (toc-depth=2); PDF-закладки — до подтем (см. header.tex).
# Ассеты (header.tex, code-to-emph.lua) берутся из каталога этого скрипта.
#
# Зависимости: pandoc, xelatex (MiKTeX/TeX Live), системные шрифты Times New Roman + DejaVu Sans Mono.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
# Ассеты лежат рядом со скриптом (плоская раскладка _СБОРКА_PDF) ЛИБО в ../assets
# (раскладка скилла: scripts/build_pdf.sh + assets/). Поддерживаем обе.
if [ -f "$HERE/header.tex" ]; then ASSETS="$HERE"; else ASSETS="$(cd "$HERE/../assets" && pwd)"; fi
TITLE=""; SUB=""; AUTHOR=""; OUT=""
while getopts "o:t:s:a:h" opt; do
  case "$opt" in
    o) OUT="$OPTARG" ;;
    t) TITLE="$OPTARG" ;;
    s) SUB="$OPTARG" ;;
    a) AUTHOR="$OPTARG" ;;
    h) sed -n '2,16p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "Неверный ключ. Запустите с -h." >&2; exit 2 ;;
  esac
done
shift $((OPTIND - 1))
[ -n "$OUT" ]   || { echo "Нужен -o OUT.pdf" >&2; exit 2; }
[ "$#" -ge 1 ]  || { echo "Нужен хотя бы один входной .md" >&2; exit 2; }

meta=(-M "title=${TITLE}")
[ -n "$SUB" ]    && meta+=(-M "subtitle=${SUB}")
[ -n "$AUTHOR" ] && meta+=(-M "author=${AUTHOR}")

# -f markdown-yaml_metadata_block: иначе «---» (тематический разрыв) при склейке файлов
# ошибочно читается как YAML-метаблок и валит сборку.
pandoc "$@" \
  -f markdown-yaml_metadata_block --pdf-engine=xelatex \
  --top-level-division=chapter --toc --toc-depth=2 \
  -L "$ASSETS/code-to-emph.lua" -H "$ASSETS/header.tex" \
  -V documentclass=book -V classoption=oneside -V fontsize=11pt \
  -V geometry:"a4paper, margin=2.5cm" \
  -V mainfont="Times New Roman" -V monofont="DejaVu Sans Mono" \
  -V lang=ru-RU -V colorlinks=true -V linkcolor=black \
  "${meta[@]}" \
  -o "$OUT"

echo "OK → $OUT"
