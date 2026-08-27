# Reference — prompts kept to read and diff against, never to run

**No profile loads anything in here**: `prompts.compose` only reaches `prompts/`
and `skills/`, so nothing in this directory is ever sent to a model or hashed
into run metadata.

| Fichero | Qué es |
|---|---|
| `DOCTOR.md` | Copia byte a byte de `ruby_version/DOCTOR.md` |
| `PATIENT.md` | Copia byte a byte de `ruby_version/PATIENT.md` |
| `DOCTOR_v1.md` | Instantánea de `../DOCTOR.md`, no del brazo Ruby. Ver abajo |

Keep the two Ruby copies frozen. The runnable descendant of the doctor prompt is
`../DOCTOR.md`.

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
  R4/5.5. Measuring it needs a doctor prompt that keeps that column on purpose,
  and no such variant exists yet.
- Patient §6 describes a JSON block of raw scores. This arm sends prose from
  `patient_profile.describe()` instead, so that section does not match the code
  and is another reason not to load these.

## `DOCTOR_v1.md`

Not a Ruby prompt. It is `../DOCTOR.md` as it stood after the style was moved
out to `skills/styles/good_doctor.md` (1.14) and before section 5's dimension
glosses were rewritten. The only difference from the current file is the wording
of the §5.1 and §5.2 glosses; role, task and research rules are the same.

It is here because that rewrite changed the composed doctor prompt hash a second
time, after `s51` had already passed the §5.1 gate. Runs are hash-comparable
within each of the three states, not across them.
