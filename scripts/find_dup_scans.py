# -*- coding: utf-8 -*-
"""Найти повторно отснятые полосы скана — по СОДЕРЖАНИЮ, а не по номерам.

Зачем. В сканах Google встречаются переснятые тетради: один и тот же разворот
попадает в файл дважды. Через конвейер это проходит молча — книга просто
получает дважды переведённый кусок в середине. Ловить по номерам страниц
нельзя: цифры во фрактуре распознаются с ошибками, и «155» читается как «455».
Проза же совпадает почти дословно (копии сняты с одного листа, отличаются
только шумом), поэтому сравниваем именно её.

Сравнение ведётся в окне соседних полос: дубль тетради лежит рядом, а
похожие абзацы из разных мест книги окном отсекаются.

Использование:
    python scripts/find_dup_scans.py <work_dir> [--window 30] [--min-ratio 0.80]
        [--json out.json]
"""
import argparse
import json
import os
import re
import sys
from difflib import SequenceMatcher

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

MIN_CHARS = 400          # короткие полосы (шмуцтитулы, пустые) не судим


def norm(text):
    text = text.replace("ſ", "s").lower()
    return re.sub(r"[^a-zäöüß]+", " ", text).strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("work_dir")
    ap.add_argument("--window", type=int, default=30)
    ap.add_argument("--min-ratio", type=float, default=0.80)
    ap.add_argument("--json", default=None)
    ap.add_argument("--structure", default=None,
                    help="structure.json: уже выброшенные полосы не судим — "
                         "иначе после дедупликации отчёт повторяет сам себя")
    a = ap.parse_args()

    skip = set()
    spath = a.structure or os.path.join(a.work_dir, "structure.json")
    if os.path.exists(spath):
        cfg = json.load(open(spath, encoding="utf-8"))
        for key in ("drop_pages", "drop_duplicates"):
            for part in str(cfg.get(key, "")).split(","):
                part = part.strip()
                if "-" in part:
                    lo, hi = (int(x) for x in part.split("-"))
                    skip.update(range(lo, hi + 1))
                elif part:
                    skip.add(int(part))
        if skip:
            print(f"учтено выброшенных полос: {len(skip)}")

    pages_dir = os.path.join(a.work_dir, "pages")
    texts = {}
    for f in sorted(os.listdir(pages_dir)):
        m = re.fullmatch(r"p(\d{4})\.txt", f)
        if not m:
            continue
        p = int(m.group(1))
        if p in skip:
            continue
        t = norm(open(os.path.join(pages_dir, f), encoding="utf-8",
                      errors="replace").read())
        if len(t) >= MIN_CHARS:
            texts[p] = t

    pages = sorted(texts)
    print(f"полос к сравнению: {len(pages)} (окно {a.window}, "
          f"порог {a.min_ratio})", flush=True)

    pairs = []
    for i, p in enumerate(pages):
        for q in pages[i + 1:]:
            if q - p > a.window:
                break
            r = SequenceMatcher(None, texts[p], texts[q]).quick_ratio()
            if r < a.min_ratio:
                continue
            r = SequenceMatcher(None, texts[p], texts[q]).ratio()
            if r >= a.min_ratio:
                pairs.append((p, q, round(r, 3)))

    print(f"пар-дублей: {len(pairs)}")
    for p, q, r in pairs:
        print(f"  полоса {p} == полоса {q}  (сходство {r})")

    # сплошные прогоны: если p..p+k дублируют q..q+k, выбрасывать надо один
    runs = []
    used = set()
    by_first = {}
    for p, q, r in pairs:
        by_first.setdefault(p, (q, r))
    for p, q, r in sorted(pairs):
        if p in used:
            continue
        length = 0
        while (p + length) in by_first and by_first[p + length][0] == q + length:
            used.add(p + length)
            length += 1
        runs.append({"первый_экземпляр": [p, p + length - 1],
                     "второй_экземпляр": [q, q + length - 1],
                     "полос": length})

    print(f"\nпрогонов-дублей: {len(runs)}")
    for r in runs:
        a1, b1 = r["первый_экземпляр"]
        a2, b2 = r["второй_экземпляр"]
        print(f"  сканы {a1}-{b1} повторены сканами {a2}-{b2} ({r['полос']} полос)")

    if runs:
        drop = []
        for r in runs:
            drop.append(f"{r['первый_экземпляр'][0]}-{r['первый_экземпляр'][1]}")
        print(f"\nв structure.json -> drop_pages добавьте: {','.join(drop)}")
        print("(выбрасываем ПЕРВЫЙ экземпляр; сверьте глазами, какая копия"
              " полнее — у неполной могут отсутствовать страницы)")

    if a.json:
        with open(a.json, "w", encoding="utf-8") as f:
            json.dump({"pairs": pairs, "runs": runs}, f,
                      ensure_ascii=False, indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
