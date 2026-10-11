---
name: asr-archive-to-edited-docs
description: >-
  Turn existing diarized ASR transcripts into raw speaker-split records, readable edited transcripts and detailed summaries. Use for cleaning lecture, seminar, interview or meeting transcripts, including archives with duplicates, split sessions and gaps. Recognition of audio itself is outside this skill.
---

# ASR archive → raw speaker-split (C) + edited transcript (A) + conspectus (B)

Raw ASR+diarization output is not a document: speaker tags are arbitrary, proper
names are mangled, and a real archive is full of duplicates, multi-part sessions,
re-readings, and gaps. This skill turns such material, recording by recording, into
two faithful, readable deliverables.

The recognition step (ASR + diarization) is upstream and out of scope here — on a
local GPU it is typically launched by the user (background jobs an assistant spawns
don't survive). This skill begins once a `*.raw.txt` of `[hh:mm:ss] SPEAKER_NN: text`
lines exists.

## Three deliverables per recording (or per session)

A **faithfulness ladder** — the same content at three levels of processing:

- **C — Raw speaker-split transcript.** The diarized ASR output, minimally
  processed: chronological turns with timestamps, **verbatim** text (recognition
  errors left as-is, no filler removal), but with the arbitrary `SPEAKER_NN` tags
  already **relabelled** to stable real roles/names (see triage below). This is the
  faithful base record — for verification, full-text search, and exact citation —
  and the source from which A and B are built.
- **A — Edited transcript.** Verbatim *in substance*, but readable: fix ASR errors
  and punctuation, drop filler and false starts, separate speakers with stable
  generic labels. Off-topic chatter (logistics, jokes, tangents) is compressed into
  *(italic parenthetical notes)* rather than deleted. Quotations of any source text
  are given as readable spoken fragments. Add timestamps `**[hh:mm:ss] Speaker.**`
  at turn boundaries and page/section markers (e.g. `≈ p. NNN`) where the group is
  reading along.
- **B — Conspectus.** Parallel to A: numbered points grouped by topic/section,
  preserving the actual line of argument and every substantive claim — a study aid,
  not a teaser. Mirror A's section/session headings and pagination.

Keep A and B **in sync**: assemble one unit, update both, then move on. For a large
archive, a steady "one session per step" rhythm keeps quality high and is easy for
the user to follow.

## Before editing: triage the raw files

Per-file `SPEAKER_NN` numbers are **per-file and meaningless** — the lecturer may be
`SPEAKER_03` in one file and `SPEAKER_00` in the next. **Relabel by content**: pick
stable, generic roles (e.g. "Лектор"/"Lecturer", "Ведущий"/"Interviewer",
"Собеседник N"/"Participant N", "(reads)" for whoever reads a source aloud) and map
each file's numbers to them by what the person actually says and does.

Then classify how the files relate — compare openings, tails, time-spans, and
line-counts:

- **Duplicate** — same content/time-span → keep the longest as canonical, ignore the rest.
- **Sequential parts** — different content, one starts where the other ends (e.g.
  "before the break" / "after the break") → splice in order into one session.
- **Re-reading** — a later session re-covers earlier material (e.g. after a holiday
  break) → do **not** duplicate; fold in only the genuinely new points as a short
  supplement to the existing section.
- **Gap** — material is simply missing (confirmed when a session opens "last time we
  established X" but X was never recorded) → record it as an explicit
  `> **Gap in recordings**` note in both documents rather than silently skipping.

## Fixing ASR errors

ASR reliably mangles proper names, foreign terms, and domain vocabulary. Correct
them using domain knowledge and context — names of people, places, works, technical
terms — and standardise spelling across the whole document (the same name often
appears several wrong ways). When a proper name is genuinely uncertain, prefer the
most likely correct form if confident, otherwise phrase around it rather than
asserting a wrong name. Preserve original-language terms where they carry meaning.

## Details and templates

See **`references/editing-spec.md`** for the concrete document skeletons (heading
hierarchy, the speaker-line format, closing-note convention) and worked examples of
the triage decisions. Adapt the labels and pagination scheme to the material —
lecture course, interview, podcast, or meeting.

## Optional: assemble into PDF

If the user wants the finished `.md` documents as a PDF and the text is non-Latin
(Cyrillic/Greek/etc.), hand off to the **markdown-to-pdf-multiscript** skill rather
than re-deriving the Pandoc+XeLaTeX recipe.
