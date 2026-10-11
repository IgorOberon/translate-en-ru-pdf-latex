---
name: transcribe-seminar
description: >-
  Transcribe a long meeting/seminar audio or video recording on THIS Windows machine with
  faster-whisper on the GPU, then (optionally) build a topic-structured конспект PDF. Use this
  whenever the user wants to расшифровать / транскрибировать / "сделать текст из" an audio or
  video file (.mp3, .m4a, .wav, .webm, .mp4, Yandex Telemost recording, lecture, семинар,
  совещание, интервью), or asks for a конспект/summary built from such a recording — even if they
  don't name faster-whisper. Especially use it for LONG recordings (tens of minutes to hours) where
  the run outlives a single Claude Code session, because this skill carries the hard-won robustness
  recipe (detached launch, single-process discipline, GPU-contention handling, incremental writes,
  completion detection) that prevents the job from silently dying or corrupting its output. Do NOT
  use it for tiny clips you could handle trivially, for non-speech audio, or for cloud/API
  transcription.
---

# Transcribe a seminar recording (robustly) and build a конспект

This skill encodes a transcription pipeline that has repeatedly bitten us in this environment.
A 2-hour recording takes tens of minutes of GPU time — longer than a Claude Code session — so the
naive "launch a background job and wait" approach loses the work over and over. The rules below are
the scar tissue. Follow them and the run survives; ignore them and you will re-transcribe the same
audio three times while two stray processes fight over the GPU.

The environment this skill assumes (verify, don't assume): Windows, Python via `py -3.9` (the bare
`python.exe` is a Store stub), `faster-whisper` + `ctranslate2` installed with CUDA, a single
consumer GPU (e.g. GTX 1660, 6 GB). Results live under `output/transcript2/` (or a fresh dir per
recording) and конспекты under `output/notesN/`.

## The robustness rules (read these first — they are the whole point)

**1. Long jobs die when the Claude Code session ends.** Both `Bash run_in_background` jobs and
`Start-Process` children are torn down when the parent Claude Code process exits or restarts. There
is no notification that survives a teardown — you just find the run frozen mid-file next session.
So: (a) launch the work **detached** with PowerShell `Start-Process` (not as the actual compute
inside a Bash background job), and (b) **tell the user to keep Claude Code open until `_DONE.txt`
appears.** Set expectations explicitly; this is the single most important instruction to convey.

**2. Do NOT create a scheduled task to gain persistence.** `schtasks /Create` is the truly
session-independent option, but the auto-mode classifier blocks it as "unauthorized persistence,"
and rightly so. Don't try to route around it. If the user genuinely needs the run to survive app
closure, *explain the trade-off and let them authorize it* — never schedule silently.

**3. Run EXACTLY ONE transcription process.** Before launching, list GPU/compute processes and make
sure none of yours is already running. Two of your processes will (a) split the single GPU, roughly
halving speed, and (b) both write the same `transcript.md` / `full_text.txt` / `run.log`, clobbering
each other into garbage. The most confusing bug in this whole saga was a "dead" run that was
actually still alive; always confirm liveness by PID and CPU, not by a frozen log.

**4. Expect GPU contention from foreign processes.** The user may have their own heavy `python.exe`
on the GPU (we saw one running elevated since hours earlier). In `nvidia-smi
--query-compute-apps`, a foreign/elevated process shows as **`[Insufficient Permissions]`** and is
**unkillable by your non-elevated tools** (`Stop-Process` / `taskkill` return "not found" or
access-denied while its CPU keeps climbing). Don't fight it. Instead **coexist**: prefer the lighter
`int8_float16` compute type so the model fits alongside it (large-v3 float16 ≈ 3 GB; two won't fit
in 6 GB and you'll OOM-fall-back to CPU, which is catastrophically slow). Expect ~0.5–0.8× realtime
while shared, ~3× when the GPU is free.

**5. Tell your processes apart from foreign ones.** Yours are killable (`Stop-Process` works); a
foreign elevated one is not. Record your launched PID to `pid.txt` and track by it. If you ever need
to clean up a mess, kill only your own PIDs; leave `[Insufficient Permissions]` processes alone.

**6. Write incrementally; detect completion by a sentinel file.** The bundled script appends each
segment to `transcript.md` / `full_text.txt` as it goes (so a kill leaves a usable partial), and at
the very end writes `transcript.json` (the clean, ordered transcript, dumped from memory and thus
immune to mid-run file clobbering) plus **`_DONE.txt`**. Poll for `_DONE.txt` to know it finished —
never assume completion from the last log line.

**7. Quote paths with spaces / Cyrillic.** Example: `D:\Мои записи\audio.mp3`.
When launching via `Start-Process -ArgumentList`, pass the script path as ONE quoted
token, e.g. `-3.9 -u "D:\…\transcribe.py"`. If you don't, it splits on the space and Python tries to
open `D:\Видео` and dies. (This wasted a whole relaunch.)

**8. Don't trust `wc -w` on Cyrillic.** It miscounts and made a perfectly good transcript look 10×
too short. Verify quality by *reading* content: check the first and last timecodes span the full
duration, count `^\*\*\[` segment lines, and sample a few segments for sensible Russian.

## Workflow

### 1. Locate the file and measure it
Find the new recording (often the newest `*_audio_only.mp3` in the project root). Get its duration
so you can give an honest ETA and set the progress denominator:
```bash
py -3.9 -c "import av; c=av.open(r'<AUDIO>'); print(round(c.duration/1e6,1))"
```

### 2. Verify the environment (don't assume it still works)
```bash
py -3.9 -c "import faster_whisper, ctranslate2; print(ctranslate2.get_cuda_device_count())"
```
Expect `>= 1`. If `0`, the run will fall back to CPU — warn the user it'll be very slow.

### 3. Check the GPU for existing/foreign processes
```
nvidia-smi --query-compute-apps=pid,used_memory,process_name --format=csv
Get-Process -Name python,py -EA SilentlyContinue | ? {$_.CPU -gt 20} | ft Id,StartTime,@{n='CPU';e={[int]$_.CPU}}
```
If one of *your* transcription processes is already running, do not launch another (rule 3). If a
foreign `[Insufficient Permissions]` process is present, plan to coexist (rule 4).

### 4. Launch ONE detached run
Use the bundled script `scripts/transcribe.py` (CUDA-DLL setup, `int8_float16`→`float16`→cpu cascade,
VAD, beam 5, no word-timestamps, incremental writes, `_DONE.txt`). Word-level timestamps are off on
purpose: a конспект only needs segment timecodes, and dropping them avoids extra work. Launch:
```powershell
$out = "D:\…\output\transcript2"
$argline = '-3.9 -u "D:\…\.claude\skills\transcribe-seminar\scripts\transcribe.py" "<AUDIO>" "' + $out + '"'
$p = Start-Process -FilePath "py" -ArgumentList $argline `
      -RedirectStandardOutput "$out\run.log" -RedirectStandardError "$out\run.err" `
      -WindowStyle Hidden -PassThru
$p.Id | Out-File -Encoding ascii "$out\pid.txt"
```
Then confirm it loaded a CUDA model (read `run.log`: `model loaded on cuda/...`, `detected
language=ru`) and that `full_text.txt` starts growing. Startup (decode + VAD over a 2 h file) takes
~3–4 min before the first segment — that's normal, not a hang.

### 5. Set expectations and poll politely
Tell the user the ETA and that **they must keep Claude Code open** until `_DONE.txt` appears. Then
poll on a long cadence (heartbeat every ~40 min, not every minute) by checking for `_DONE.txt` and
tailing `run.log`. Don't busy-wait. Across a session boundary the detached run may have been killed
(rule 1) — on resume, re-check: if `_DONE.txt` is absent and the PID is gone with no error in
`run.err`, it was torn down; relaunch (rule 3 first).

### 6. Verify the result
```bash
grep -cE '^\*\*\[' <out>/transcript.md          # segment count
grep -oE '^\*\*\[[0-9:]+\]' <out>/transcript.md | tail -1   # last timecode ≈ full duration?
```
Read the head, a middle sample, and the tail. Confirm the last timecode reaches the measured
duration and the text is sensible Russian.

### 7. Build the конспект (if asked)
See `references/konspekt-format.md` for the exact LaTeX format, box environments, the **no-names /
roles-only** convention, the timecode macro, and the build/QA steps (lualatex, 0 Type3). Read the
*whole* transcript before writing — a good конспект is organized by topic and decision, not by
chronology. Then register the new PDF in `README.md` and `PROJECT_STATE.md`.

## Bundled resources
- `scripts/transcribe.py` — the robust, parameterized transcription script. Args: `<audio> [outdir]
  [beam]`. Edit only if you must; it embeds rules 4, 6, 7 above.
- `scripts/run_transcribe.bat` — optional wrapper that handles redirection if you ever DO get
  user authorization for a scheduled task (rule 2); otherwise prefer the `Start-Process` launch.
- `references/konspekt-format.md` — конспект structure, style, and build steps.
