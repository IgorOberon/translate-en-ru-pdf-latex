#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for procutils.py: PipelineLock (захват, реентерабельность детей,
перехват протухшего) и run_mineru (таймаут -> rc=124, дерево убито).
Exit 1 on failure."""
import os
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import procutils as P  # noqa: E402

CHECKS = []


def check(name, ok, extra=""):
    print(("PASS" if ok else "FAIL"), name)
    if not ok and extra:
        print("   ", extra)
    CHECKS.append(ok)


def test_lock():
    os.environ.pop("FREETRANSLATE_LOCK", None)
    lk = P.PipelineLock(name="test_procutils", note="test")
    lk.acquire()
    check("lock: file created on acquire", lk.path.exists())
    # ребёнок держателя проходит мгновенно через env FREETRANSLATE_LOCK
    t0 = time.time()
    P.PipelineLock(name="test_procutils").acquire()
    check("lock: holder's child re-enters instantly", time.time() - t0 < 1)
    lk.release()
    check("lock: file removed on release", not lk.path.exists())

    # протухший чужой лок (мёртвый pid, старый mtime) перехватывается
    os.environ.pop("FREETRANSLATE_LOCK", None)
    lk2 = P.PipelineLock(name="test_procutils", ttl=5)
    lk2.path.write_text('{"pid": 99999999, "note": "dead"}', encoding="utf-8")
    old = time.time() - 3600
    os.utime(lk2.path, (old, old))
    lk2.acquire(wait=False)
    check("lock: stale lock taken over", lk2._owned)
    lk2.release()
    os.environ.pop("FREETRANSLATE_LOCK", None)

    # kill не снимает замок, но mtime свежий: по одному возрасту замок казался
    # бы живым до ttl. С проверкой живости PID мёртвый держатель снимается
    # СРАЗУ (регресс #7), даже при большом ttl и свежем mtime.
    try:
        import psutil  # noqa: F401
        os.environ.pop("FREETRANSLATE_LOCK", None)
        lk3 = P.PipelineLock(name="test_procutils", ttl=99999)
        lk3.path.write_text('{"pid": 99999999, "note": "killed"}',
                            encoding="utf-8")   # свежий mtime (только что создан)
        lk3.acquire(wait=False)
        check("lock: dead holder taken over immediately despite fresh mtime",
              lk3._owned)
        lk3.release()
        os.environ.pop("FREETRANSLATE_LOCK", None)
    except ImportError:
        check("lock: dead-pid takeover (psutil absent — skipped)", True)


def test_parse_unresolved():
    check("parse_unresolved: normal line",
          P.parse_unresolved("restored exact: 34, repaired damaged: 2, "
                             "unresolved: 5") == 5)
    check("parse_unresolved: zero", P.parse_unresolved("unresolved: 0") == 0)
    check("parse_unresolved: absent line -> None (not 0)",
          P.parse_unresolved("какой-то другой вывод") is None)
    check("parse_unresolved: empty/None input",
          P.parse_unresolved("") is None and P.parse_unresolved(None) is None)


def test_untranslated_ok():
    # горсть провалов -> продолжаем
    check("untranslated_ok: 1/30 -> продолжить", P.untranslated_ok(1, 30))
    check("untranslated_ok: 2/2 (<=2) -> продолжить", P.untranslated_ok(2, 2))
    check("untranslated_ok: 0/500 -> продолжить", P.untranslated_ok(0, 500))
    # доля ровно на пороге 2%
    check("untranslated_ok: 6/300 (2%) -> продолжить", P.untranslated_ok(6, 300))
    # массовый недобор -> падаем
    check("untranslated_ok: 270/629 -> die", not P.untranslated_ok(270, 629))
    check("untranslated_ok: 10/100 (10%>2%) -> die",
          not P.untranslated_ok(10, 100))
    check("untranslated_ok: kept=None -> die", not P.untranslated_ok(None, 30))
    check("untranslated_ok: своя толерантность 20%",
          P.untranslated_ok(10, 100, tol=0.20))


def test_run_mineru_timeout():
    tmp = Path(tempfile.mkdtemp())
    fake = tmp / "mineru.bat"
    fake.write_text("@echo off\nping -n 30 127.0.0.1 >NUL\n", encoding="ascii")
    orig = os.environ["PATH"]
    os.environ["PATH"] = str(tmp) + os.pathsep + orig
    try:
        t0 = time.time()
        # This test owns only the fake child's tree. Never enumerate/kill real
        # MinerU or a user's concurrent pipeline from an installation smoke test.
        with patch.object(P, "_mineru_procs_psutil", return_value=[]), \
                patch.object(P, "_mineru_pids_cim", return_value=[]):
            rc = P.run_mineru(["-p", "x", "-o", "y"], tmp / "log.txt", timeout=3)
        dt = time.time() - t0
    finally:
        os.environ["PATH"] = orig
    check("run_mineru: hang -> rc=124", rc == P.TIMEOUT_RC, f"rc={rc}")
    check("run_mineru: tree killed promptly", dt < 20, f"{dt:.0f}s")
    check("run_mineru: log file written", (tmp / "log.txt").exists())


SELFKILL_CHILD = '''# -*- coding: utf-8 -*-
import os, sys
sys.path.insert(0, sys.argv[2])
import psutil
from unittest.mock import patch
from procutils import reap_mineru
# Exercise the real lineage/filter logic, but every kill is mocked and the
# process inventory contains only this test's ancestors. No host-wide cleanup.
mine = psutil.Process()
lineage = [mine] + mine.parents()
for p in lineage:
    p.info = p.as_dict(attrs=["pid", "name", "cmdline"])
with patch.object(psutil, "process_iter", return_value=lineage), \
        patch.object(psutil.Process, "kill") as kill:
    n = reap_mineru()
    assert n == 0 and not kill.called, "own lineage selected for cleanup"
open(sys.argv[1], "w", encoding="utf-8").write("ALIVE %d %d" % (os.getpid(), n))
'''


def test_reap_does_not_kill_itself():
    """reap_mineru() не должен убивать собственное дерево процессов.

    Так конвейер терял extract_chunked.py: translate_book зовёт его командой
    «python extract_chunked.py … --mineru-timeout 3600», то есть слово
    «mineru» стоит в командной строке САМОГО ДОЧЕРНЕГО процесса. venv-питон
    поднимает настоящий интерпретатор отдельным потомком с той же командной
    строкой — и этот двойник проходит фильтр «python + mineru», а исключение
    «это я» его не покрывает. children(recursive=True) двойника содержит нас,
    и мы убиваем сами себя: ни traceback, ни кода выхода, ни строчки в логе.
    """
    import subprocess
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        child = d / "child.py"
        child.write_text(SELFKILL_CHILD, encoding="utf-8")
        marker = d / "marker.txt"
        # «mineru» в argv — тот самый триггер
        r = subprocess.run([sys.executable, "-X", "utf8", str(child),
                            str(marker), str(ROOT / "scripts"),
                            "--mineru-timeout", "3600"],
                           capture_output=True, text=True, timeout=180)
        check("reap_mineru: не убивает сам себя при «mineru» в argv",
              marker.exists() and r.returncode == 0,
              f"rc={r.returncode}, marker={marker.exists()}, "
              f"stderr={r.stderr[-200:]}")


def test_own_lineage():
    mine = P.own_lineage()
    check("own_lineage: содержит собственный pid", os.getpid() in mine, mine)
    check("own_lineage: содержит не только себя", len(mine) >= 2, mine)


def main():
    test_lock()
    test_parse_unresolved()
    test_untranslated_ok()
    test_own_lineage()
    test_reap_does_not_kill_itself()
    test_run_mineru_timeout()
    failed = CHECKS.count(False)
    print(f"\n{len(CHECKS) - failed}/{len(CHECKS)} passed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
