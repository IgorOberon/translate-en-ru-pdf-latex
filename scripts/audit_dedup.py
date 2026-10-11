# -*- coding: utf-8 -*-
"""Приёмка дедупликации: не выброшено ли уникальное, не осталось ли дублей.

Два вопроса, на которые обязан ответить любой прогон с drop_pages:

1. У КАЖДОЙ выброшенной полосы должен найтись уцелевший двойник. Если у
   выброшенной полосы двойника нет — из книги вырезан уникальный текст, и
   перевод молча неполон. Это главная опасность агрессивного порога.
2. Среди оставленных полос дублей быть НЕ должно, иначе кусок книги
   переведётся дважды.

Использование:
    python scripts/audit_dedup.py <work_dir> --structure structure.json
        [--window 40] [--min-ratio 0.6]
"""
import argparse
import json
import os
import re
import sys
from difflib import SequenceMatcher

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

MIN_CHARS = 300


def norm(text):
    text = text.replace("ſ", "s").lower()
    return re.sub(r"[^a-zäöüß]+", " ", text).strip()


def parse_ranges(spec):
    out = set()
    for part in str(spec or "").split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            lo, hi = (int(x) for x in part.split("-"))
            out.update(range(lo, hi + 1))
        else:
            out.add(int(part))
    return out


def best_match(text, others, window_keys):
    best, best_r = None, 0.0
    for q in window_keys:
        t = others.get(q)
        if not t:
            continue
        if SequenceMatcher(None, text, t).quick_ratio() < 0.5:
            continue
        r = SequenceMatcher(None, text, t).ratio()
        if r > best_r:
            best, best_r = q, r
    return best, best_r


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("work_dir")
    ap.add_argument("--structure", default=None)
    ap.add_argument("--window", type=int, default=40)
    ap.add_argument("--min-ratio", type=float, default=0.60)
    a = ap.parse_args()

    cfg = {}
    path = a.structure or os.path.join(a.work_dir, "structure.json")
    if os.path.exists(path):
        cfg = json.load(open(path, encoding="utf-8"))
    # Судим только пересъёмки: у них обязан быть уцелевший двойник. Страницы
    # из drop_pages (титул, издательское оглавление) выброшены намеренно, и
    # требовать для них двойника бессмысленно.
    intentional = parse_ranges(cfg.get("drop_pages", ""))
    dup_spec = cfg.get("drop_duplicates")
    dropped = (parse_ranges(dup_spec) if dup_spec is not None
               else intentional)
    if dup_spec is None:
        print("!! в structure.json нет drop_duplicates — судим весь "
              "drop_pages; намеренно выброшенные полосы попадут в отчёт")
    all_dropped = intentional | dropped

    texts = {}
    for f in sorted(os.listdir(os.path.join(a.work_dir, "pages"))):
        m = re.fullmatch(r"p(\d{4})\.txt", f)
        if not m:
            continue
        t = norm(open(os.path.join(a.work_dir, "pages", f), encoding="utf-8",
                      errors="replace").read())
        if len(t) >= MIN_CHARS:
            texts[int(m.group(1))] = t

    kept = {p: t for p, t in texts.items() if p not in all_dropped}
    drop = {p: t for p, t in texts.items() if p in dropped}
    print(f"полос с текстом: {len(texts)}; выброшено {len(drop)}, "
          f"оставлено {len(kept)}")

    # Главный критерий — не сходство с соседями, а факт: есть ли текст
    # выброшенной полосы в СОБРАННОЙ книге. Сравнение в окне ошибается в обе
    # стороны (двойник бывает дальше окна, а шум OCR занижает сходство даже
    # у настоящих копий), поэтому, если book.md уже собран, ищем в нём.
    book_path = os.path.join(a.work_dir, "book.md")
    book = None
    if os.path.exists(book_path):
        book = re.sub(r"[^a-zäöüß]+", "",
                      open(book_path, encoding="utf-8").read()
                      .replace("ſ", "s").lower())

    orphans, both_out = [], []
    for p, t in sorted(drop.items()):
        if book is not None:
            flat = re.sub(r"[^a-zäöüß]+", "", t)
            anchors = [flat[i:i + 40]
                       for i in range(60, min(len(flat) - 40, 1400), 120)]
            if not anchors:
                continue
            hits = sum(1 for x in anchors if x in book)
            if hits:
                continue
            orphans.append((p, "нет в book.md", 0.0))
            continue
        win = [q for q in kept if abs(q - p) <= a.window]
        q, r = best_match(t, kept, win)
        if r >= a.min_ratio:
            continue
        win_d = [x for x in drop if x != p and abs(x - p) <= a.window]
        q2, r2 = best_match(t, drop, win_d)
        if r2 >= a.min_ratio:
            both_out.append((p, q2, round(r2, 2)))
        else:
            orphans.append((p, q, round(r, 2)))

    print(f"\n1a) ОБЕ КОПИИ ВЫБРОШЕНЫ: {len(both_out)} полос")
    if both_out:
        print("    (страницы нет в книге; верните одну копию в drop_pages)")
        for p, q, r in both_out[:40]:
            print(f"    полоса {p}: её двойник {q} ({r}) тоже выброшен")

    print(f"\n1b) ВЫБРОШЕНО БЕЗ ДВОЙНИКА ВООБЩЕ: {len(orphans)} полос")
    if orphans:
        print("    (уникальный текст, которого в книге больше нет)")
        for p, q, r in orphans[:40]:
            print(f"    полоса {p}: лучшее совпадение {q} = {r}")

    left = []
    ks = sorted(kept)
    for i, p in enumerate(ks):
        for q in ks[i + 1:]:
            if q - p > a.window:
                break
            if SequenceMatcher(None, kept[p], kept[q]).quick_ratio() < 0.6:
                continue
            r = SequenceMatcher(None, kept[p], kept[q]).ratio()
            if r >= a.min_ratio:
                left.append((p, q, round(r, 2)))
    print(f"\n2) ДУБЛИ СРЕДИ ОСТАВЛЕННЫХ: {len(left)} пар")
    for p, q, r in left[:25]:
        print(f"   полосы {p} и {q}: сходство {r}")

    return 1 if (orphans or left or both_out) else 0


if __name__ == "__main__":
    sys.exit(main())
