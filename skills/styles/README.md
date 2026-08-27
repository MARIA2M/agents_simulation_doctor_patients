# Doctor communication styles

Nine files, one per style, plus `styles.yaml`. Eight are ported from
`ahead_agent_ckakalou/ahead_agent/prompts/doctor_styles/` (1.14); `good_doctor.md`
is not a port but the style `prompts/DOCTOR.md` carried inline until now.

A style is loaded the way every skill is loaded — the profile names it, the code
concatenates it, the composed prompt is hashed into `run_meta` (§5.1, 0.4):

```yaml
skills:
  doctor:
    - styles/biopsychosocial
```

An arm is that plus two lines: see `config/style-biopsychosocial.yaml`.

## What crossed over, and what did not

Each source file had a fixed 11-section schema. The port splits it in two, by
one rule: **the prompt gets how the doctor talks, the registry gets what we
expect to see and how we would recognise it.**

| Source section | Goes to | Why |
|---|---|---|
| 1 Style ID | file name + `styles.yaml` key | — |
| 2 Clinical purpose | prompt, rewritten | Kept as framing of the encounter, with the construct names taken out. |
| 3 Effect on illness perceptions | `styles.yaml: hypotheses.illness` | A prediction, not an instruction. |
| 4 Effect on treatment beliefs | `styles.yaml: hypotheses.treatment` | Same. |
| 5 Doctor behaviours | prompt | This is the style. |
| 6 Prohibited behaviours | prompt | This is the style. |
| 7 Question style | prompt | This is the style. |
| 8 Response length / turn-taking | prompt, and `turn_budget` in the registry | Also the one adherence signal that needs no model to measure. |
| 9 Target constructs | **dropped** | See below. |
| 10 Style-adherence markers | `styles.yaml: markers` | The measuring instrument. In the prompt it would be a checklist to copy. |
| 11 Experimental notes | `styles.yaml: notes`, where still true here | Most of it was about the elicitation arm. |

Four things were deliberately left behind.

**Section 9, target constructs.** Every source file listed which constructs the
style would make visible and which would stay hidden. In this arm that goes
straight into the prompt of an agent that later scores those same constructs and
may return NA. Telling the doctor in advance which dimensions are meant to come
out empty corrupts 1.10 and 3.2, which exist to measure exactly that. Kept as
hypotheses in the registry, where nothing reads them into a model.

**The phases.** The source composes per phase — `doctor_bipq.md`, `doctor_bmq.md`
— and `styles.yaml` marked each style `compatible_phases: [bipq, bmq]`. It is an
elicitation arm: the doctor administers the instrument. 1.3 took the phases out
of this code, and all eight styles declared both phases anyway, so the field
discriminated nothing. Dropped rather than carried, because a dead field is an
invitation to bring the questionnaire back in through the side door.

**`Do not reveal B-IPQ, BMQ, construct labels, questionnaire names, or scoring
logic`**, repeated verbatim at the end of all eight prohibition lists. Already in
`DOCTOR.md` §4, and repeating it here would name two instruments eight more
times in a prompt that is trying not to think about them.

**The `expected_*_effects` as results.** They are written as predictions — "May
improve…", "More likely to reveal…" — and no run stands behind any of them. They
are inherited as questions for 6.5. Renamed `hypotheses` so the word itself
resists being read as a finding.

## The §5.1 gate, and the experiment it unblocks

**Passed 2026-08-25** on `s51-nb-1` / `s51-bps-1`: `glm-4.7-flash:q8_0` doctor,
`dolphin-llama3` patient, CLL-001, 2 repeats per arm. Same model, same
temperature, same commit; only the style file differed. Doctor turn length
separated with no overlap (40.9 against 66.5 words), and `narrowly_biomedical`
opened no psychosocial ground unprompted in either run while `biopsychosocial`
opened family at turn 3 and emotion at turn 2.

Two things that run also established, and that constrain how the next one is
read:

- **`turn_budget` is directional, not compliance.** Every style overshoots its
  own declared sentence count and stacks questions into turns that say "one
  question at a time". Compare styles against each other, never against the
  number in their own file.
- **The patient fabricates.** In `s51-nb-1` r1 the patient claimed medication
  and headaches; CLL-001 is watch-and-wait with neither. Treat that as
  stochastic noise at this n, not as a finding, and expect it to add variance
  between arms that has nothing to do with the style.

### Next: the same pair across the corpus

Not launched. Ten patients × 2 repeats × 2 arms = 40 consultations, same shape
as `e4-1` per arm. **Commit first** — `s51` ran with `dirty: true` and is
therefore untraceable, which is acceptable for a dry run and not for this.

```bash
./venv-hpc/bin/python run_batch.py --profile style-narrowly_biomedical --repeats 2 --run-id s52-nb-1
./venv-hpc/bin/python run_batch.py --profile style-biopsychosocial   --repeats 2 --run-id s52-bps-1
```

Four gates, fixed before the run, all doctor-level and all readable from the
existing transcripts and `batch.json`:

| | gate | passes if |
|---|---|---|
| A | **Topic selection** — who raises psychosocial ground first | `narrowly_biomedical` opens it first in ≤1 of 20 consultations; `biopsychosocial` in ≥10 of 20 |
| B | **Relative turn length** | mean doctor words/turn higher for `biopsychosocial` in ≥8 of 10 patients. No absolute sentence check |
| C | **Forbidden-topic violations** | `narrowly_biomedical` exploring family, work, identity, stigma or emotional meaning unprompted: <20% of its consultations |
| D | **`stop_reason`** | every consultation closes `doctor`. Any `max_turns` means the style broke the closing behaviour and the batch is not analysable |

Only if A–D hold does patient behaviour get looked at, and only after that
NA and MAE. A style that fails D has changed the doctor's stopping rule rather
than its questioning, and every number downstream inherits that.

## The bug that was not copied

`prompt_builder.py:20` in the source spells one style
`high_psysician_control_paternalistic`, while both the file and its `styles.yaml`
entry say `physician`. That style is unreachable: the correct name fails
validation, the misspelling passes validation and then fails to find the file.

The fix is not a careful spelling. It is
`test_every_style_has_a_file_and_every_file_a_style` in `tests/test_styles.py`,
which fails on any id that exists on one side and not the other.

## `good_doctor.md`

`DOCTOR.md` used to fix a communication style in prose: warm, empathic,
patient-centred, adapt to the patient, never directive, plus a psychosocial
exploration phase with four example questions. That is a style, and it
contradicts `narrowly_biomedical`, `high_physician_control_paternalistic` and
`consumerist` outright — a doctor told both things at once resolves the
contradiction however the model feels like, and a §5.1 test that came out flat
could not be told apart from the base prompt simply winning.

So those sentences moved here, word for word, and `local.yaml` and `hpc.yaml`
load `styles/good_doctor`. The default arm is unchanged in content and now has a
name. `DOCTOR.md` keeps the role, the task, the dimensions and the research
rules, and says nothing about tone.

**It is a reference condition, not a proven best.** The name is a label for the
arm the project ran under before styles were files. No run has shown it to be
the best of the nine — that question is 6.5 — and nothing downstream should read
the filename as a result.

It is also no longer verbatim. `DOCTOR.md` carried four literal example
questions ("How do you make sense of what's happening with your health?" and
three more); they were dropped, because a reference condition that scripts the
doctor's exact phrasing is a stronger steer than any of the eight ports it is
meant to be compared against. The tone sentences it still carries are pinned by
`test_the_style_left_the_base_prompt_and_is_in_good_doctor`; the example
questions deliberately are not. The change was made before any batch ran under
it. It remains the only style that names dimensions outright — inherited from
`DOCTOR.md` word for word.

One consequence to keep in view: the composed doctor prompt changed, so its hash
changed. Runs up to and including `e4-1` are **pre-styles** and their
`prompts.skills` reads `{"doctor": [], "patient": []}`. They are still the
baseline arm, but they are not hash-comparable with anything run after this.
