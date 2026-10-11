# -*- coding: utf-8 -*-
"""
Robust long-audio transcription via faster-whisper (large-v3, Russian by default) on Windows GPU.

Usage:
    py -3.9 -u transcribe.py "<audio path>" ["<out dir>"] [beam]

Why it is written this way (see SKILL.md "robustness rules"):
  * Cascade compute type int8_float16 -> float16 -> cpu/int8, so it FITS alongside another GPU
    process (rule 4) and never silently OOM-falls to CPU without trying the light type first.
  * Incremental writes of transcript.md / full_text.txt (a kill leaves a usable partial), and at the
    end transcript.json (clean, ordered, dumped from memory -> immune to file clobbering) + _DONE.txt
    as the completion sentinel (rule 6). Poll _DONE.txt to know it finished.
  * word_timestamps=False: a конспект needs only segment timecodes; dropping word alignment is free
    speed.
Run EXACTLY ONE of these at a time (rule 3) and launch it DETACHED via Start-Process (rule 1).
"""
import os
import sys
import json
import time

LANG = "ru"


def add_cuda_dll_dirs():
    """Make the pip nvidia-* CUDA DLLs importable (Windows)."""
    try:
        import importlib.util
        spec = importlib.util.find_spec("nvidia")
        if spec is None or not spec.submodule_search_locations:
            return []
        added = []
        for base in spec.submodule_search_locations:
            for sub in ("cublas", "cudnn"):
                binp = os.path.join(base, sub, "bin")
                if os.path.isdir(binp):
                    try:
                        os.add_dll_directory(binp)
                        os.environ["PATH"] = binp + os.pathsep + os.environ.get("PATH", "")
                        added.append(binp)
                    except Exception as e:
                        print(f"[warn] add_dll_directory {binp}: {e}", flush=True)
        return added
    except Exception as e:
        print(f"[warn] cuda dll setup: {e}", flush=True)
        return []


def hms(t):
    t = int(round(t))
    return f"{t//3600:02d}:{(t%3600)//60:02d}:{t%60:02d}"


def audio_duration(path):
    try:
        import av
        c = av.open(path)
        d = c.duration / 1e6
        c.close()
        return float(d)
    except Exception:
        return 0.0


def load_model(WhisperModel):
    # int8_float16 FIRST so the model fits next to a foreign GPU process (rule 4).
    last = None
    for device, ct in [("cuda", "int8_float16"), ("cuda", "float16"), ("cpu", "int8")]:
        try:
            print(f"[info] loading large-v3 on {device}/{ct} ...", flush=True)
            m = WhisperModel("large-v3", device=device, compute_type=ct)
            print(f"[ok] model loaded on {device}/{ct}", flush=True)
            return m, device, ct
        except Exception as e:
            print(f"[warn] {device}/{ct} failed: {e}", flush=True)
            last = e
    raise RuntimeError(f"Could not load model: {last}")


def main():
    if len(sys.argv) < 2:
        print("usage: transcribe.py <audio> [outdir] [beam]", flush=True)
        sys.exit(2)
    audio = sys.argv[1]
    out = sys.argv[2] if len(sys.argv) > 2 else os.path.join(os.path.dirname(audio), "transcript")
    beam = int(sys.argv[3]) if len(sys.argv) > 3 else 5
    os.makedirs(out, exist_ok=True)

    add_cuda_dll_dirs()
    from faster_whisper import WhisperModel

    total = audio_duration(audio) or 1.0
    print(f"[info] audio={audio}", flush=True)
    print(f"[info] out={out} beam={beam} dur={hms(total)}", flush=True)

    t0 = time.time()
    model, device, ct = load_model(WhisperModel)

    segments, info = model.transcribe(
        audio, language=LANG, task="transcribe", beam_size=beam,
        vad_filter=True, vad_parameters=dict(min_silence_duration_ms=500),
        word_timestamps=False, condition_on_previous_text=False,
        temperature=[0.0, 0.2, 0.4, 0.6, 0.8, 1.0],
    )
    print(f"[info] detected language={info.language} p={info.language_probability:.3f} "
          f"audio_dur={info.duration:.0f}s", flush=True)

    md = open(os.path.join(out, "transcript.md"), "w", encoding="utf-8")
    md.write("# Транскрипт\n\n")
    md.write(f"_Модель: large-v3 ({device}/{ct}); язык: {info.language}; "
             f"длительность: {hms(info.duration)}_\n\n")
    txt = open(os.path.join(out, "full_text.txt"), "w", encoding="utf-8")

    seg_list = []
    n = 0
    last_report = time.time()
    for seg in segments:
        n += 1
        text = seg.text.strip()
        seg_list.append({"id": seg.id, "start": round(seg.start, 3), "end": round(seg.end, 3),
                         "text": text, "avg_logprob": round(seg.avg_logprob, 3),
                         "no_speech_prob": round(seg.no_speech_prob, 3),
                         "compression_ratio": round(seg.compression_ratio, 3)})
        md.write(f"**[{hms(seg.start)}]** {text}\n\n")
        txt.write(text + " ")
        now = time.time()
        if now - last_report > 5:
            md.flush(); txt.flush()
            spd = seg.end / max(1e-6, now - t0)
            eta = (total - seg.end) / max(1e-6, spd)
            print(f"[progress] {hms(seg.end)} / {hms(total)} ({100.0*seg.end/total:5.1f}%) "
                  f"segs={n} speed={spd:.2f}x eta={eta/60:.1f}min", flush=True)
            last_report = now

    md.close(); txt.close()
    with open(os.path.join(out, "transcript.json"), "w", encoding="utf-8") as f:
        json.dump({"language": info.language, "duration": info.duration,
                   "device": device, "compute_type": ct, "segments": seg_list},
                  f, ensure_ascii=False, indent=1)
    with open(os.path.join(out, "_DONE.txt"), "w", encoding="utf-8") as f:
        f.write(f"segments={n} duration={info.duration:.1f}s device={device}/{ct} "
                f"elapsed_min={(time.time()-t0)/60:.1f}\n")
    print(f"[done] segments={n} elapsed={(time.time()-t0)/60:.1f} min", flush=True)


if __name__ == "__main__":
    main()
