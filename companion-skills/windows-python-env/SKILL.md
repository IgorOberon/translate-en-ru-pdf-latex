---
name: windows-python-env
description: Set up and debug Python/ML tooling environments on Windows (PowerShell) without the classic traps. Use this skill whenever the user works in PowerShell with pip/venv/conda, sees WinError 1314 or 10054, gets "not recognized as a command" for an installed tool, has a Cyrillic Windows username or Cyrillic paths, needs CUDA-enabled PyTorch, sees mojibake instead of Russian text in the console, or reports that a console program froze for no reason. Russian phrasings that must trigger it too — «python не находится», «pip не ставит пакет», «кракозябры в консоли», «torch не видит GPU», «настрой окружение на Windows». Apply it proactively when writing installation instructions for any Windows user.
---

# Windows + Python/ML environment — trap map

First move on any misbehaving machine: run the bundled doctor —
`powershell -ExecutionPolicy Bypass -File scripts\env_doctor.ps1` — it checks
the venv marker, `where.exe python` (Store stub / PATH order),
`torch.cuda.is_available()`, `HF_HOME` vs Cyrillic profile, ExecutionPolicy and
console encoding, and prints an OK/FAIL table with the cure per line
(read-only; exit code = number of FAILs).

## The venv discipline (solves half of all mysteries)

- Project on a **latin path without spaces** (`D:\project`), venv inside it:
  ```powershell
  py -3.12 -m venv venv
  .\venv\Scripts\Activate.ps1
  ```
- The `(venv)` marker in the prompt is the contract. Every new window = re-activate.
  A console window that was killed/replaced silently loses it — the #1 cause of
  sudden `'tool' not found` for tools that worked five minutes ago.
- `(base)` in the prompt = Anaconda hijacked the shell. Its Python is often ancient
  (3.8) and fails modern installs with `No matching distribution found`. Don't
  fight conda — just activate the project venv ON TOP; verify with
  `where.exe python` (venv path must be FIRST) and `python --version`.
- If `Activate.ps1` is blocked ("running scripts is disabled"):
  `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` (once).
- PowerShell eats square brackets: quote extras — `pip install "mineru[core]"`.
- **The Windows Store `python` stub**: on a machine without real Python (or in
  Git-Bash), `python` may be a Store redirector that exits code 49 doing
  nothing. Prefer the `py` launcher (`py -3.12 …`) or the venv's explicit
  `.\venv\Scripts\python.exe`.
- `Start-Process` and friends: ALWAYS quote paths with spaces/Cyrillic; an
  unquoted `D:\Мои записи\a.mp3` silently truncates at the space.

## Cyrillic username / paths

Some tools crash on non-ASCII cache paths (`C:\Users\Имя пользователя`). Relocate caches to a
latin path; set BOTH persistently and for the current session (setx-style vars do
NOT affect the already-open window):

```powershell
[Environment]::SetEnvironmentVariable("HF_HOME","D:\hfcache","User")
$env:HF_HOME = "D:\hfcache"
```

Same pattern for any per-session knob (e.g. `$env:MINERU_VIRTUAL_VRAM_SIZE=8`) —
it dies with the window; re-set after reopening.

## Symlinks: WinError 1314

Model caches (HuggingFace) use symlinks; Windows denies them to normal users.
Fix once: Settings -> For developers -> **Developer Mode** ON (no reboot).
Alternative (worse): run the downloading step elevated.

## CUDA PyTorch (the silent 70x slowdown)

Plain `pip install torch` on Windows frequently installs the CPU build.
Check and cure:

```powershell
python -c "import torch; print(torch.__version__, torch.cuda.is_available())"
# '+cpu ... False'  ->
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu128 --force-reinstall
```

Index by GPU generation: `cu121`/`cu124` for RTX 30/40, `cu128` for RTX 50.
Symptom downstream: GPU tools report `gpu_memory: 1 GB` or run at seconds-per-item
while the GPU idles.

## localhost networking: WinError 10054

VPN clients, corporate proxies and antivirus web-shields intercept `localhost`.
For local servers (LM Studio, Ollama, dev APIs): use `127.0.0.1` explicitly and
bypass the system proxy in code (`urllib.request.ProxyHandler({})`); add the app
to antivirus exclusions if resets persist.

## Console traps

- **QuickEdit freeze**: a mouse click inside a console selects text and PAUSES the
  running program until Enter. Title bar shows "Select". For long runs disable:
  window menu -> Properties -> untick QuickEdit Mode.
- **Mojibake** (`Р’РµСЃ...` instead of Russian): the FILE is fine (UTF-8); the
  console decodes as cp1251. Read with `Get-Content file -Encoding UTF8`, or
  switch session: `chcp 65001` /
  `[Console]::OutputEncoding=[Text.Encoding]::UTF8`. When writing files from
  PowerShell, force `-Encoding UTF8`.
- **Task Manager lies about GPU**: default graphs (3D/Copy/Video) don't include
  CUDA. Switch a graph to "Cuda", or use `nvidia-smi` (add `-l 2` to watch).
  The honest memory pair: "Dedicated GPU memory" (real VRAM) vs "Shared GPU
  memory" (spillover into RAM — should stay ~0; growth = imminent slowdown).
- Long-run checklist: sleep disabled in power settings (display-off is fine),
  QuickEdit off, `(venv)` confirmed, disk has a few GB free.

## Zombie processes

Closing a console does not reliably terminate every descendant of a GPU tool.
Inspect its recorded PID, command line and children; terminate only confirmed
owned processes, then verify their exit and GPU use. Do not kill unrelated
Python processes by name. Zombies also HOLD
FILES: reinstalling a package "in use" fails until the holder dies.

## Version-fingerprint pattern for shipped scripts

Make every script print a banner first (`>> tool.py v6.1 loaded`). Then
"downloaded file is truncated/stale" and "wrong python answered" are diagnosed in
one second: no banner -> re-download; wrong version -> wrong file or wrong env.

## Companion skills

- **transcribe-seminar** — the long-GPU-job rules built on top of this
  environment (detached launch, one-process rule, incremental output + DONE
  sentinel files).
- **local-llm-lmstudio** — localhost server ops and VRAM budgeting.
