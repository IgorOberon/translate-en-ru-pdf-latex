#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""rescue_plaques.py v3 — спасение текстовых плашек, уехавших картинками.

MinerU классифицирует затенённые выносные рамки (определения, постулаты,
ключевые утверждения — с центрированным заголовком на сером фоне) как
картинки: в markdown попадает кроп пикселей, текст внутри не переводится.

ВАЖНО про метод. Пере-распознавать кропы тем же MinerU нельзя: его VLM
стохастически виснет в генерации на вырезанных плашках (проверено — зависания
на часы). Надёжный путь — ЗРЕНИЕ агента (Claude): он читает кроп как картинку
и переводит плашку сразу в LaTeX. Поэтому конвейер делает только ДЕТЕКЦИЮ и
ОТЧЁТ, а восстановление текста выполняет vision-агент. Три шага:

  1) detect  — найти кропы-кандидаты (геометрия + нет подписи Figure/Рисунок),
               выписать их в <out>.json и человекочитаемый отчёт. Быстро, без
               GPU, зависнуть нечем.
  2) (агент) — vision-агент открывает каждый кроп, классифицирует
               (plaque|figure|formula|text|other) и для plaque пишет
               title_ru + body_ru (готовый LaTeX). Результат — JSON-массив
               {hash, kind, title_ru, body_ru}. См. процедуру в АГЕНТ.md.
  3) patch   — вставить боксы плашек в главу(ы) .tex по hash и убрать
               дубли-заголовки, которые MinerU выдал отдельными секциями.

Usage:
  python rescue_plaques.py detect <extracted.md> --json cand.json --report r.md
  python rescue_plaques.py patch <vision.json> <chapter.tex>
  python rescue_plaques.py patch-dir <vision_dir> <chapters_dir>   # пакетно
"""
import argparse
import difflib
import json
import re
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

print(">> rescue_plaques.py v3 (detect / vision / patch)", flush=True)


# --------------------------------------------------------------- детекция
def find_content_list(md):
    cands = sorted(Path(md).parent.glob("*content_list.json"))
    cands = [c for c in cands if "_v2" not in c.name] or cands
    return cands[0] if cands else None


def detect(md_path):
    """Кропы-кандидаты в плашки: без подписи, широкая-низкая геометрия."""
    from PIL import Image
    md_path = Path(md_path)
    cl = find_content_list(md_path)
    if not cl:
        return None, "content_list.json не найден — детекция плашек пропущена"
    items = json.loads(cl.read_text(encoding="utf-8"))
    out = []
    for it in items:
        if it.get("type") != "image" or any(it.get("image_caption") or []):
            continue
        f = md_path.parent / it["img_path"]
        try:
            w, h = Image.open(f).size
        except Exception:
            continue
        if w / h >= 2.0 and h <= 800:
            out.append({"hash": Path(it["img_path"]).stem, "abs": str(f),
                        "page": it.get("page_idx"), "w": w, "h": h})
    return out, None


# ------------------------------------------------- промпт для vision-агента
VISION_PROMPT_HEAD = """\
# Vision-проход по кропам-кандидатам в текстовые плашки

Ты — vision-агент. MinerU вырезал перечисленные ниже фрагменты страниц как
картинки; часть из них — не рисунки, а ТЕКСТОВЫЕ ПЛАШКИ (определения,
постулаты, ключевые утверждения: центрированный заголовок + абзац на сером
фоне). Их текст не попал в перевод, и его нужно восстановить.

Для КАЖДОГО кропа из списка:
1. Открой файл инструментом Read (это картинка — прочитай её глазами).
2. Классифицируй `kind`: `plaque` (текстовая плашка) | `figure` (настоящий
   рисунок/график) | `formula` (выключная формула) | `text` (обычный абзац)
   | `other` (не уверен). Сомневаешься — ставь `other`, НЕ `plaque`.
3. Только для `plaque`: переведи содержимое на русский и запиши
   - `title_ru` — заголовок плашки (пустая строка, если заголовка нет),
   - `body_ru`  — тело плашки, ГОТОВЫЙ LaTeX: математика в `$...$`,
     спецсимволы (`%`, `&`, `#`, `_`) экранированы, никаких `\\begin{figure}`
     и `\\includegraphics`. Термины — по глоссарию проекта, если он дан.

Результат запиши в файл `{OUT_JSON}` — JSON-массив по одному объекту на
каждый кроп (включая не-плашки):

```json
[{"hash": "<hash из списка, скопируй ТОЧНО, без пробелов>",
  "kind": "plaque", "title_ru": "...", "body_ru": "..."}]
```

После этого оператор вставит плашки командой:
`python scripts/rescue_plaques.py patch {OUT_JSON} <глава.tex>`
(или `patch-dir` для пакета глав).

## Кропы
"""


def write_vision_prompt(cands, path, out_json):
    lines = [VISION_PROMPT_HEAD.replace("{OUT_JSON}", str(out_json))]
    for c in cands:
        lines.append(f"- hash `{c['hash']}` | стр. {c['page']} | "
                     f"{c['w']}x{c['h']} px | {c['abs']}")
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")


# ------------------------------------------------------------------ патч
SEC_RE = re.compile(r"\\subs(?:ub)?section\*?\{([^{}]*)\}(\s*\\label\{[^}]*\})?",
                    re.S)


def _norm(s):
    return " ".join(re.sub(r"[^а-яёa-z0-9 ]", " ", (s or "").lower()).split())


def _box(title, body):
    t, b = (title or "").strip(), (body or "").strip()
    head = (r"\centering\textbf{\large " + t + r"}\par\smallskip" if t else "")
    return ("\n\\begin{center}\n\\fbox{\\parbox{0.92\\linewidth}{" + head
            + "\n\\raggedright\\itshape " + b + "}}\n\\end{center}\n")


def patch(vision_json, tex_path):
    """Вставить боксы плашек в главу и убрать дубли-заголовки."""
    items = json.loads(Path(vision_json).read_text(encoding="utf-8"))
    plaques = [x for x in items if x.get("kind") == "plaque"
               and (x.get("body_ru") or "").strip()]
    tex = Path(tex_path)
    text = tex.read_text(encoding="utf-8")
    # 1) вставка боксов по хэшу картинки
    paras = text.split("\n\n")
    done, miss = 0, []
    titles = []
    for p in plaques:
        h = p["hash"].replace(" ", "")
        idx = next((k for k, par in enumerate(paras)
                    if "includegraphics" in par
                    and h[:32] in par.replace(" ", "")), None)
        if idx is None:
            miss.append(h[:12])
            continue
        paras[idx] = _box(p.get("title_ru"), p["body_ru"])
        titles.append(_norm(p.get("title_ru")))
        done += 1
    text = "\n\n".join(paras)
    # 2) снять дубли-заголовки (MinerU выдал заголовок плашки ещё и секцией)
    titles = [t for t in titles if t]
    deduped = [0]

    def _drop(m):
        head = _norm(m.group(1))
        if head and max((difflib.SequenceMatcher(None, head, t).ratio()
                         for t in titles), default=0) > 0.75:
            deduped[0] += 1
            return ""
        return m.group(0)
    if titles:
        text = SEC_RE.sub(_drop, text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    if done or deduped[0]:
        tex.write_text(text, encoding="utf-8")
    return done, len(plaques), miss, deduped[0]


# ------------------------------------------------------------------ main
def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser("detect")
    d.add_argument("md")
    d.add_argument("--json", default=None, help="куда выписать кандидатов")
    d.add_argument("--report", default=None, help="человекочитаемый отчёт")
    d.add_argument("--prompt", default=None,
                   help="готовый промпт для vision-агента (по умолчанию "
                        "plaques_vision_prompt.md рядом с отчётом)")

    p = sub.add_parser("patch")
    p.add_argument("vision_json")
    p.add_argument("tex")

    pd = sub.add_parser("patch-dir")
    pd.add_argument("vision_dir")
    pd.add_argument("chapters_dir")

    a = ap.parse_args()

    if a.cmd == "detect":
        cands, err = detect(a.md)
        if err:
            print(f">> plaques: {err}")
            return
        print(f">> plaques: кандидатов в текстовые плашки: {len(cands)}"
              + (" (нужен vision-проход, см. АГЕНТ.md)" if cands else ""))
        if a.json:
            Path(a.json).write_text(json.dumps(cands, ensure_ascii=False,
                                               indent=1), encoding="utf-8")
        if a.report and cands:
            lines = ["# Кропы-кандидаты в текстовые плашки (нужен vision-проход)",
                     "", "Открой каждый Read'ом, классифицируй, для plaque —",
                     "переведи в LaTeX; затем: rescue_plaques.py patch <json> <tex>",
                     ""]
            for c in cands:
                lines.append(f"- стр.{c['page']} {c['w']}x{c['h']} {c['abs']}")
            Path(a.report).write_text("\n".join(lines) + "\n", encoding="utf-8")
        if cands and (a.prompt or a.report or a.json):
            anchor = Path(a.prompt or a.report or a.json)
            prompt = anchor if a.prompt \
                else anchor.parent / "plaques_vision_prompt.md"
            out_json = prompt.parent / "plaques_vision.json"
            write_vision_prompt(cands, prompt, out_json)
            print(f">> plaques: промпт для vision-агента: {prompt}")

    elif a.cmd == "patch":
        done, tot, miss, dd = patch(a.vision_json, a.tex)
        print(f">> plaques patch: вставлено {done}/{tot}, дублей-заголовков "
              f"снято {dd}" + (f", не найдено: {', '.join(miss)}" if miss else ""))

    elif a.cmd == "patch-dir":
        vd, cd = Path(a.vision_dir), Path(a.chapters_dir)
        tot_done = tot_dd = 0
        for jf in sorted(vd.glob("*.json")):
            tex = cd / f"{jf.stem}.tex"
            if not tex.is_file():
                continue
            done, tot, miss, dd = patch(jf, tex)
            tot_done += done
            tot_dd += dd
            if done or dd:
                print(f"{jf.stem}: вставлено {done}, дублей снято {dd}"
                      + (f", не найдено {len(miss)}" if miss else ""))
        print(f">> итого боксов {tot_done}, дублей-заголовков снято {tot_dd}")


if __name__ == "__main__":
    main()
