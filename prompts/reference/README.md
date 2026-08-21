# Reference — the Ruby arm's prompts, verbatim

`DOCTOR.md` and `PATIENT.md` here are byte-for-byte copies of
`ruby_version/{DOCTOR,PATIENT}.md`. They are here to read and diff against, and
**no profile loads them**: `prompts.compose` only reaches `prompts/` and
`skills/`, so nothing in this directory is ever sent to a model or hashed into
run metadata.

Keep them frozen. The runnable descendant of the doctor prompt is
`../DOCTOR-ruby.md`, which is this file minus section 5.

## What section 5 was

The Ruby doctor prompt ended with the report it had to write: a
`Score | Rationale` table for B-IPQ, another for BMQ, and the 0–10 anchors. Two
reasons that cannot come along:

- The report is a separate step here (ARCHITECTURE §4, stage 3). During the
  consultation the doctor holds a view; it does not write it down.
- The column order is `Score | Rationale`, so the justification was generated
  after the number and was decorative (2.1, INHERITED_ISSUES R3). The
  replacement order is `evidence → reasoning → score`, and it belongs in the
  report prompt, not this one.

## What else to look at while reading these

- Doctor §3.1/§3.2 "What to listen for" and patient §3.1/§3.2 "How it manifests
  in conversation" are the same table written from both sides — the mirror of
  R4/5.5. `../DOCTOR-cues.md` keeps that column on purpose, to measure it.
- Patient §6 describes a JSON block of raw scores. This arm sends prose from
  `patient_profile.describe()` instead, so that section does not match the code
  and is another reason not to load these.
