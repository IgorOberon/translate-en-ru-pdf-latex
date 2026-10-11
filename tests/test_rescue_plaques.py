#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for rescue_plaques.py: detect on a synthetic fixture (PIL images +
content_list.json) incl. vision-prompt generation, patch (box insertion by
hash, duplicate-heading removal, idempotency). Exit 1 on failure."""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import rescue_plaques as rp  # noqa: E402

HASH = "a" * 64
CHECKS = []


def check(name, ok, extra=""):
    print(("PASS" if ok else "FAIL"), name)
    if not ok and extra:
        print("   ", extra)
    CHECKS.append(ok)


# ------------------------------------------------------------------ detect
def make_fixture():
    from PIL import Image
    tmp = Path(tempfile.mkdtemp())
    (tmp / "images").mkdir()

    def img(name, w, h):
        Image.new("RGB", (w, h), "lightgray").save(tmp / "images" / name)

    img(f"{HASH}.jpg", 1200, 300)      # кандидат: широкий-низкий, без подписи
    img("b" * 64 + ".jpg", 1200, 300)  # есть подпись Figure -> не кандидат
    img("c" * 64 + ".jpg", 500, 500)   # квадрат -> не кандидат
    img("d" * 64 + ".jpg", 1200, 900)  # слишком высокий -> не кандидат
    items = [
        {"type": "image", "img_path": f"images/{HASH}.jpg",
         "image_caption": [], "page_idx": 3},
        {"type": "image", "img_path": "images/" + "b" * 64 + ".jpg",
         "image_caption": ["Figure 1.2 A block on a slope"], "page_idx": 4},
        {"type": "image", "img_path": "images/" + "c" * 64 + ".jpg",
         "image_caption": [], "page_idx": 5},
        {"type": "image", "img_path": "images/" + "d" * 64 + ".jpg",
         "image_caption": [], "page_idx": 6},
        {"type": "text", "text": "прочий текст", "page_idx": 6},
    ]
    (tmp / "pages_content_list.json").write_text(
        json.dumps(items), encoding="utf-8")
    md = tmp / "pages.md"
    md.write_text(f"![](images/{HASH}.jpg)\n", encoding="utf-8")
    return tmp, md


def test_detect():
    tmp, md = make_fixture()
    cands, err = rp.detect(md)
    check("detect: no error", err is None, str(err))
    check("detect: exactly one candidate", len(cands) == 1,
          json.dumps(cands, ensure_ascii=False))
    if cands:
        check("detect: right hash and page",
              cands[0]["hash"] == HASH and cands[0]["page"] == 3)

    # CLI: --report дополнительно порождает промпт для vision-агента
    r = subprocess.run(
        [sys.executable, "-X", "utf8", str(ROOT / "scripts" / "rescue_plaques.py"),
         "detect", str(md), "--json", str(tmp / "cand.json"),
         "--report", str(tmp / "report.md")],
        capture_output=True, text=True, encoding="utf-8", timeout=60)
    prompt = tmp / "plaques_vision_prompt.md"
    check("detect CLI: exit 0", r.returncode == 0, r.stderr[-500:])
    check("detect CLI: vision prompt written", prompt.exists())
    if prompt.exists():
        t = prompt.read_text(encoding="utf-8")
        check("detect CLI: prompt lists the crop with abs path",
              HASH in t and str(tmp) in t)
        check("detect CLI: prompt names the output json",
              "plaques_vision.json" in t)


# ------------------------------------------------------------------- patch
TEX = r"""Вводный абзац главы.

\begin{figure}[h]
\centering
\includegraphics[width=0.8\linewidth]{images/%HASH%.jpg}
\end{figure}

\subsubsection*{Второй закон Ньютона}

Текст после плашки остаётся.
""".replace("%HASH%", HASH)

VISION = [
    {"hash": HASH, "kind": "plaque", "title_ru": "Второй закон Ньютона",
     "body_ru": "В инерциальной системе отсчёта $\\vec F = m\\vec a$."},
    {"hash": "e" * 64, "kind": "figure", "title_ru": "", "body_ru": ""},
]


def test_patch():
    tmp = Path(tempfile.mkdtemp())
    tex = tmp / "ch05.tex"
    tex.write_text(TEX, encoding="utf-8")
    vj = tmp / "ch05.json"
    vj.write_text(json.dumps(VISION, ensure_ascii=False), encoding="utf-8")

    done, tot, miss, dd = rp.patch(vj, tex)
    text = tex.read_text(encoding="utf-8")
    check("patch: one box inserted", (done, tot) == (1, 1),
          f"done={done} tot={tot} miss={miss}")
    check("patch: crop replaced by fbox with the body",
          HASH not in text and "\\fbox" in text
          and "инерциальной системе" in text)
    check("patch: duplicate heading removed",
          dd == 1 and "subsubsection" not in text)
    check("patch: surrounding text intact",
          "Вводный абзац главы." in text
          and "Текст после плашки остаётся." in text)

    # идемпотентность: повторный патч ничего не меняет
    done2, _tot2, miss2, dd2 = rp.patch(vj, tex)
    check("patch: idempotent re-run",
          done2 == 0 and dd2 == 0
          and tex.read_text(encoding="utf-8") == text,
          f"done2={done2} dd2={dd2} miss2={miss2}")


def main():
    test_detect()
    test_patch()
    failed = CHECKS.count(False)
    print(f"\n{len(CHECKS) - failed}/{len(CHECKS)} passed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
