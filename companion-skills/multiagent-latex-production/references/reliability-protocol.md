# Reliability protocol for parallel LaTeX workers

The failure modes below are not hypothetical — every one killed real workers in a
~470-page, ~370-figure multi-agent translation. The fixes are what made the run
finish. Read this before dispatching a big wave.

## The three killers

1. **The no-progress watchdog (~600 s).** A worker that opens the PDF and reads a
   whole section's pages/figures *before writing anything* produces no tool output
   for minutes and gets killed with nothing on disk. This is the most common and
   most wasteful death.
2. **Socket drops / rate-limits.** With many figure-heavy agents in flight, the
   transport drops. Frequently it kills only the agent's *final message* — the
   files it wrote are already on disk. If you treat "no summary" as "failed" and
   re-dispatch blindly, you redo finished work and can double-write.
3. **Partial completion.** A worker dies halfway: 4 of 7 figure files written. You
   must detect what's there and dispatch only the remainder.

## The worker-prompt contract

Every dispatched worker prompt must hard-code write-early, incremental behaviour.
A template that worked:

```
You own <unit> (e.g. §6.3), source pages PDF index P1–P2.
1. FIRST, create <path>/sec6_3.tex with the section heading and a one-line
   stub. Do this before reading the figures.
2. Translate the prose into Russian (российская традиция), section by section,
   appending to the file as you go. Preserve every numbered equation + its number.
3. Figures ONE AT A TIME: for each figure, view only that figure's page region,
   write figures/ch06/fig6_N.tex (TikZ or \includegraphics per hybrid-figure-
   triage), then move to the next. Do NOT pre-render all figures.
4. Return ONLY: unit id, files written (paths), figure count, any TODO. No prose,
   no file contents.
```

The two non-negotiables: **write within the first 2–3 tool calls**, and **one
figure at a time**. Both keep tool output flowing so the watchdog never fires.

## Wave loop (orchestrator side)

```
for wave in slices(units, size<=3):
    dispatch(wave)                      # <=3 concurrent
    wait()
    for u in wave:
        if Glob(u.expected_files):      # DISK is the source of truth
            mark_done(u); compile_check(u)
        else:
            requeue(u)                  # genuinely missing only
    build_audit(master)                 # errors/undefined/multiply/missing == 0?
    update_ledger()                     # PROGRESS.md: status + any lesson
```

Key points:
- **Audit from disk, not from the summary.** A returned summary is a convenience;
  the file's existence + a clean standalone compile is the truth.
- **Idempotent units.** Because a unit is one file, re-dispatching a half-done
  unit just overwrites it cleanly — no merge needed. Keep units file-disjoint so
  two workers never touch the same file.
- **Keep the orchestrator light.** It dispatches, globs, compiles, audits, and
  records — it does not itself translate or draw. Its context is the scarce
  resource; spending it on returned prose is the slow way to run out.

## Standalone compile per unit (catch errors before the master)

A worker (or the orchestrator) compiles the one section with a tiny wrapper that
`\input`s the shared preamble + just that section, so an error is localized to the
unit instead of surfacing 60 chapters later in the master build. `translate-book-
to-latex`'s `compile_retry.py` handles the transient out-of-memory retries if you
are on LuaLaTeX; on pdfLaTeX + T2A (the "российская традиция" path, see
latex-pdf-font-audit) builds are cheaper and a couple of direct passes suffice —
just run pdflatex twice so refs resolve, then `build_audit.py` the log.

## Windows / PowerShell sandbox notes

- The shell here is PowerShell: `$null` not `/dev/null`, `$env:VAR` not `$VAR`,
  backtick for line continuation.
- The command sandbox classifier false-flags some *mixed* commands. Observed
  triggers: `Remove-Item` in the same command as a LaTeX here-string, or as a
  string containing `\hbox`, `\documentclass`, `\input`, a `/NN` page token, or
  `~`. Fix: split into separate commands and keep deletes simple and named.
- Strip stray combining accents (U+0301 acute, U+0300 grave) at assembly — they
  ride in on copied Russian text and break the T2A build. A .NET replace works:
  `(Get-Content f -Raw) -replace [char]0x0301,'' -replace [char]0x0300,''`.
