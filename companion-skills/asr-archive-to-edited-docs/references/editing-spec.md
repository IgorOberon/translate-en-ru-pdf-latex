# Editing spec: document skeletons, conventions, worked examples

Concrete patterns for the A (edited transcript) and B (conspectus) deliverables.
Adapt labels/pagination to the material; the structure generalizes across lecture
courses, interviews, podcasts, and meetings.

## A — edited transcript skeleton

```markdown
# <Chapter / Topic title>

*(Structure note: how the material is organized; what was edited.)*

> **Gap in recordings.** <only if something is missing — say what and how you know>

## <Major section>

### Session <date> — <subtopic> (≈ p. NNN)

**[00:00:22] Interviewer.** <clean question/turn>

**[00:01:26] Lecturer.** <clean answer; ASR fixed; filler dropped>
*(logistics/tangent compressed to an italic note)*

**[00:08:40] Participant 1 (reads).** «<source quotation as a readable fragment>»

*(Session <date> finished: <what was covered>. Next session (<date>) — <what's next>.)*
```

Conventions:
- **Speaker label** in bold, after the timestamp: `**[hh:mm:ss] Label.**`. Use
  stable generic roles, not the raw `SPEAKER_NN`.
- **Timestamps** at turn boundaries (not every sentence). Keep the `[hh:mm:ss]` from
  the raw file.
- **Tangents/byt** → `*(italic parenthetical)*` — compress, don't delete; the reader
  should know it happened without wading through it.
- **Pagination / section markers** (`≈ p. NNN`, `≈ С. NNN`) wherever the group reads
  a source text, so a reader can follow along.
- **Closing note** in italics at the end of each session: what was covered + a
  pointer to the next session. This makes a long multi-session document legible and
  resumable.

## B — conspectus skeleton

```markdown
# <Chapter / Topic title> (conspectus)

*(Structure note + which terms/names were normalized.)*

## <Major section>

### Session <date> — <subtopic> (≈ p. NNN)

**1. <point>.** <claim, with the actual reasoning, key terms **bolded**, pagination.>
**2. <point>.** …

→ next (<date>): <what follows>. *(Session <date> finished on <where>.)*
```

The conspectus must preserve the **line of argument** and every substantive claim —
it is a study aid, not a blurb. Mirror A's headings and pagination so the two
documents are navigable in parallel.

## Worked triage examples

These illustrate the "classify the files" step; the *decision* matters more than the
specific content.

- **Three files looked like duplicates → actually sequential parts.** Same nominal
  topic, but openings/time-spans showed: part 1 ends at the break, part 2 opens
  "after the break", part 3 is a ~17-min finale. Decision: splice in order as one
  session, not pick one. (The lecturer's `SPEAKER_NN` differed in each file — relabel
  by content.)

- **A later file was a re-reading.** After a holiday break the group re-read an
  earlier intro. Decision: do **not** duplicate that intro; fold only the genuinely
  new remarks into the existing section as a short supplement.

- **A gap was inferred, not seen.** A session opened "last time we established that
  tragedy is superior to epic" — but that discussion was never recorded. Decision:
  add a `> **Gap in recordings**` note where it belongs, and carry on.

- **Two speakers, roles assigned by behaviour.** In an interview, the opener who asks
  questions and says "welcome to the studio" is the Interviewer; the one giving long
  answers about their own career is the guest. The raw `SPEAKER_02`/`SPEAKER_00`
  numbers are arbitrary — assign by what each says.

## ASR correction — illustration

ASR mangles names/terms; fix with domain knowledge and standardise across the doc.
Examples of the *kind* of fix (one mangled form → intended): a surname rendered three
different ways → one correct spelling; an acronym garbled phonetically → the real
acronym; a transliterated foreign term → the established term. If a name is genuinely
uncertain, write around it rather than assert a wrong one. State near the top of each
document which names/terms you normalized, so the reader knows the transcript was
curated.

## Working rhythm for a large archive

Assemble **one unit at a time** (one session, or one duplicate-resolved group),
update **both** A and B, then report briefly and pause. This keeps the two documents
in sync, makes quality reviewable, and lets the user steer ("continue") session by
session instead of receiving an unreviewable bulk dump.
```
