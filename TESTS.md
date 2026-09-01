# What the suite covers

A living inventory of `tests/`. For each file: what it guards, against which
concrete failure, and whether it is needed. **Updated whenever a test is added,
removed or changed.** It is checked against [TASKS.md](TASKS.md) and against the
eight invariants of [ARCHITECTURE.md](ARCHITECTURE.md) §9.

**321 `test_` functions and 511 cases**, recounted on 2026-09-01 — 296 functions
and 486 cases on 2026-08-31, and 346 cases with 198 functions on 2026-08-26. None
of them touches the network: the LLM is replaced by scripted replies.

The 511 come out with `AHEAD_GRAPH_TESTS=1`; without the variable it is 509 and 2
skipped, which are the two end-to-end tests — the only ones that build the graph
and therefore import `langgraph`.

The jump from 486 to 511 is 5 in `test_llm.py` (N10) and 20 in
`test_replay_server.py`, and no test changed its meaning.

This document sat at 202 functions between 2026-08-27 and 2026-08-31 while three
files were added that did not appear in the table: `test_coverage.py` (3.2),
`test_ablation.py` (5.4) and `test_fidelity.py` (3.5). And on 2026-09-01 it was
five short on `test_llm.py`, which had gone from 11 to 16 with the N10 tests
without anyone recording it. **If the count here does not match `grep`, `grep`
wins.**

The function count comes from `grep -c '^def test_' tests/test_*.py`; the case
count needs pytest. Recount before trusting the number.

The cases **do not depend on the tests alone**: `test_config.py`,
`test_metadata.py` and `test_prompts.py` are parametrised over `config/*.yaml`,
so **every new arm adds cases to tests nobody has touched**. The two style
profiles of 1.14 added 7 on their own. A number going up without a test being
written is not a regression: it is new profiles. To recount:

```bash
./venv-hpc/bin/python -m pytest tests/ --collect-only -q | sed 's/::.*//' | sort | uniq -c
```

```bash
AHEAD_GRAPH_TESTS=1 ./venv-local/bin/python -m pytest tests/ -q
```

Key: **✅** needed · **📄** documents more than it verifies.

---

## Summary

| File | Functions | Cases | What it guards | Stage |
|---|---|---|---|---|
| `conftest.py` | — | — | Shared scaffolding: `PATIENT`, `speaks`, `note`, `profile`, `in_mode`, and the `scripted`, `state`, `make_run_profile` fixtures | — |
| `test_config.py` | 22 | 28 | The profiles load; none of them leaves a setting to the server | 1 |
| `test_corpus.py` | 9 | 40 | The 10 patients, their ground truth, and where each number came from | 1 |
| `test_metadata.py` | 13 | 15 | The provenance is collected whole and survives the disk | 1 |
| `test_llm.py` | 16 | 16 | What travels on each call, and **how the request changes on a retry** | 2/4 |
| `test_prompts.py` | 16 | 16 | Deterministic composition from disk, and its hashes | 2 |
| `test_styles.py` | 16 | 95 | The doctor's nine styles: register, form, content and arms | 2 |
| `test_tools.py` | 6 | 12 | Reading the call, and building each arm's tools | 2 |
| `test_nodes.py` | 7 | 7 | The loop, and the isolation of the profile | 2 |
| `test_patient_profile.py` | 12 | 28 | Score → behaviour, and the gap left where there is no score | 2 |
| `test_coverage_hint.py` | 12 | 18 | The `coverage_hint` arm | 3 |
| `test_notes.py` | 9 | 14 | The `working_notes` arm | 3 |
| `test_report.py` | 32 | 42 | Schema, parsing, gaps, retry, writing to disk | 3 |
| `test_evaluation.py` | 17 | 17 | MAE, bias, bands, the two correlations, and D12 | 5 |
| `test_causes.py` | 17 | 17 | Cosine, matching, taxonomy, recorded method | 5 |
| `test_evaluate.py` | 8 | 8 | The entry point of 4.7 — it was never in this table | 5 |
| `test_coverage.py` | 34 | — | 3.2 and 2.4: quote integrity, the four states, mean and spread | 6 |
| `test_fidelity.py` | 38 | 50 | 3.5: did the patient play its profile?, and the false positives that would make it useless | 6 |
| `test_ablation.py` | 17 | — | 5.4: which sentence is removed and how the two conditions are compared | 7 |
| `test_replay_server.py` | 20 | 20 | The viewer: which consultations a batch says it holds, whose they are, and what one carries once read off disk | 7 |

### `conftest.py`

What the suite shares. It lives here because it used to live in a test file:
`test_nodes` exported `PATIENT`, `speaks`, `scripted` and `state` to three other
files, and `test_coverage` exported `profile` and `in_mode` to a fourth. Touching
`PATIENT` broke files that never mentioned it, and import order started to
matter.

`PATIENT` is watch-and-wait on purpose (C1: the `specific_*` subscales have no
drug to be about) and carries the whole `belief_profile`, which is what the
isolation test looks for in the doctor's context.

---

## Phase 1 — Foundation

### `test_config.py` — 22 functions, 28 cases

All ✅. The rejection block exists because **a missing setting does not raise: the
server decides it** (§12), and then the metadata lies.

| Test | What it prevents |
|---|---|
| `test_shipped_profile_loads` | A profile in the repo that does not load |
| `test_shipped_profile_survives_first_load_from_gpfs` | Timeout < 300 s: the first blob off GPFS aborts (§6.1) |
| `test_each_load_is_independent` | State shared between profiles |
| `test_temperature_is_required_for_every_role` | A role sampling at whatever the server decides |
| `test_zero_temperature_is_accepted` | A falsiness check throwing away 0.0, which is a temperature |
| `test_missing_model_is_rejected` | — |
| `test_missing_turn_limit_is_rejected` | Without `max_turns` nothing stops a doctor that does not close (1.5) |
| `test_missing_paths_are_rejected` | A bare `KeyError` halfway through a batch |
| `test_declared_profile_must_match_filename` | Mislabelled runs in the metadata |
| `test_unknown_profile_is_rejected` | — |
| `test_the_coverage_arms_are_accepted` | — |
| `test_a_retired_mode_is_rejected` | An old profile with `declare` running as if nothing had changed |
| `test_an_unquoted_off_is_caught_and_named` | Bare `off` is `False` in YAML: it would read as "no coverage" while meaning "nobody chose" |
| `test_a_quoted_working_notes_is_caught_and_named` | The mirror of the previous trap: here the danger is **quoting it**. `"off"` is a non-empty string, and would switch the arm on with nobody asking |
| `test_ollama_url_can_be_redirected` | — |
| `test_causes_is_not_a_numeric_dimension` | Something iterating `b_ipq` and averaging a list of strings |

The rejections depend on `make_run_profile` **replacing** the block rather than
merging it: omitting a key is how you check that it is required. Merging would
turn four tests green with nothing holding them up.

### `test_corpus.py` — 9 functions, 40 cases

Rewritten on 2026-08-26, when `patients/` became the normalised CK corpus. What
changed substantively: the corpus is **no longer** the Ruby arm's, and **C1 was
retired** — CK scores the `specific_*` subscales without a prescription too.

| Test | Need |
|---|---|
| `test_corpus_has_ten_patients` | ✅ |
| `test_profile_carries_ground_truth` | ✅ every dimension is a number, which also covers the key existing, and now within range: B-IPQ 0–10, BMQ 1–5. It no longer requires NA without a prescription |
| `test_patients_is_the_normalised_ck_corpus` | ✅ the one that replaces 0.3. It re-runs the normalisation over `patientsCK/` and requires it to reproduce the file byte for byte. Without it, `patients/` is a hand-edited directory and the provenance of the ground truth is lost |
| `test_the_ruby_corpus_is_frozen` | ✅ what 0.3 protected, moved to `sintetic_patients/patients_version1/`. The `runs/historic/` batches were scored against that corpus, so re-analysing them requires it to stay intact |
| `test_the_item_mean_returns_the_one_to_five_scale` | ✅ 5 cases. The denominator is the item count times 5, not a divisor: `21/25` is a sum of 21 over 5 items, i.e. 4.2, and never the proportion 0.84. Floor and ceiling included |
| `test_an_unexpected_maximum_is_refused` | ✅ the important one of the two. A maximum that does not add up means a different item count, and normalising it anyway puts a value on a different scale without anyone noticing. It is CLL-003's `7/10` case |
| `test_the_normaliser_leaves_the_beliefs_alone` | ✅ only the BMQ changes shape. If the script touched `b_ipq`, the ground truth of eight dimensions would depend on it without anyone having decided so |

### `test_metadata.py` — 13 functions, 15 cases ✅

`test_the_temperature_recorded_is_the_one_that_will_be_sent` compares against
`llm.sampling_options`, which is what puts the temperature into the request:
storing a number in the metadata is worth nothing if a different one travels, and
they are two separate readings of the same block (§12).

The rest guard things that are easily lost:
`test_code_provenance_answers_both_questions` (a commit without `dirty` names
different code), `test_compute_records_both_hostname_and_nodelist` (the §6.3
signal), `test_started_at_carries_a_timezone`, `test_serialises_completely`.

---

## Phase 2 — The agentic loop

### `test_llm.py` — 16 ✅

Three blocks. **What travels**: temperature and `num_ctx` always explicit, seed
only when set, `keep_alive` on every call (without it the server drops the model
after five minutes), tools only when given, and the report is written by the
doctor's model. **What is retried**: an empty reply (19% of the previous corpus),
a transport failure up to `MAX_ATTEMPTS`, and every retry leaves an event.

`test_a_reply_with_only_tool_calls_is_not_empty` stops the empty-turn retry from
swallowing the normal case: the doctor speaks *through* the tool, so its
`content` is empty by design.

**How the request changes on a retry** — the five of N10, and what they guard is
a distinction, not a rule:

- `test_a_transport_failure_is_retried_with_the_identical_request` — the server
  did not answer, so the correct request is the same one. Changing it here would
  measure something else for no reason.
- `test_an_empty_reply_at_temperature_zero_is_retried_with_a_different_draw` —
  the mirror, and **the one that cost two consultations**: the model did answer,
  and answered nothing. At T=0 the next draw is the same nothing, so the three
  attempts reproduced the failure instead of recovering from it.
- `test_a_role_already_sampling_above_the_floor_is_left_alone` — the floor only
  raises. Dropping the doctor's temperature to 0.3 on a retry would change its
  behaviour halfway through a consultation.
- `test_a_pinned_seed_moves_too_when_the_reply_was_empty` — with the seed pinned
  the draw is identical however the temperature moves, so raising it alone is not
  enough.
- `test_the_temperature_a_clean_call_sends_is_the_declared_one` — the one holding
  §12 up: attempt 1 sends what the profile says, and `metadata.sampling` does not
  lie. What went out on a retry lives in its event, as `retry_temperature`.

### `test_prompts.py` — 16 ✅

File resolution, ordered composition (skills before resources, each role only its
own), the separator between fragments, and hashes.

The three hash tests are the engine of Phase 6:
`test_the_hash_is_of_the_composed_prompt_not_the_base_file` is what allows a
change of result to be attributed to a change of prompt.

`test_the_doctor_never_sees_the_scale_during_the_consultation` is worth
flagging: the rubric only reaches the report. A doctor with the anchors in hand
would be scoring while it talks, which is the elicitation arm through another
door.

`test_an_arm_that_adds_a_tool_argument_changes_the_tool_hash` closes a provenance
hole: tool descriptions are instructions, and until now nobody hashed them. The
`notes` argument's description could be rewritten — changing what the doctor
records — and `metadata.json` came out identical.

### `test_styles.py` — 16 functions, 95 cases ✅

The doctor's nine communication styles (1.14): eight ported from
`ahead_agent_ckakalou` and `good_doctor`, which is what `DOCTOR.md` carried
inside it. None of them touches the network — whether the style *changes* the
transcript cannot be asked here, and that is the live half of the §5.1 test.

Four blocks, each guarding a different failure:

**The registry against the directory.**
`test_every_style_has_a_file_and_every_file_a_style` is the correction of the
original's bug: `prompt_builder.py:20` wrote
`high_psysician_control_paternalistic` and the file said `physician`, so that
style was unreachable from both sides. The spelling was never the fix.

**What a style may say.** `test_no_style_names_the_instrument_or_the_scale` and
`test_no_style_tells_the_doctor_which_dimensions_will_stay_empty`. The second is
the one that matters: section 9 of the original told the doctor which constructs
would be visible and which empty, and it is the same agent that later scores
those constructs and can return NA. Naming a dimension is not the problem —
`DOCTOR.md` §5 lists them all; predicting them for it is. They live in
`styles.yaml`, and `test_the_hypotheses_stayed_out_of_the_prompt` checks that
they stayed there.

**Composition and hashes.**
`test_each_style_gives_the_doctor_prompt_its_own_hash`: nine styles, nine
distinct hashes, or two arms are a single run in the provenance.
`test_the_anchors_still_do_not_reach_a_doctor_with_a_style` repeats
`test_prompts`'s invariant with a skill loaded: a style is a new route for the
scale to reach the consultation.

**The profiles on disk.** `test_every_profile_names_exactly_one_style` is a new
project rule, not a code check: after 1.14 the doctor's style is always a file
somebody chose. A profile with no style runs the unnamed arm this task exists to
eliminate. `test_the_style_left_the_base_prompt_and_is_in_good_doctor` guards
both halves of the move: if the sentence is still in `DOCTOR.md`, every style
contradicts it; if it is not in `good_doctor.md`, the arm everything before was
measured under has changed with nobody deciding it.

**The shape of the file.** `test_every_style_has_the_same_three_sections` and
`test_a_style_constrains_about_as_much_as_it_prescribes`. The second comes from a
real failure: `good_doctor` was written with five instructions and **one**
prohibition, against four in the eight ported ones. Unequal constraint pressure
is a difference between arms that nobody chose, and it falls exactly on the axis
the styles are meant to vary.

### `test_tools.py` — 6 functions, 12 cases ✅

`test_a_broken_call_raises_rather_than_ending_the_consultation` is the important
one: a broken call is **not** a decision to close. Confusing them would put
truncated consultations into the corpus as if the doctor had finished them.

`test_building_the_tools_never_touches_the_one_the_module_ships` walks the four
modes: `doctor_tools` copies before adding arguments, and if it mutated the
constant the first arm would leave the following ones contaminated inside the
same process — and a batch runs the arms in the same process.

`test_the_patient_reply_goes_back_as_the_tool_result` guards the channel: inside
a tool result the doctor cannot tell our words from the patient's, and
`Evidence.quote` has to be a literal line of theirs.

### `test_nodes.py` — 7 ✅

It holds invariant 1, the only one mandatory since Stage 2:
`test_the_patient_profile_never_reaches_the_doctor` serialises everything sent to
the doctor and looks for every value of the `belief_profile`. Its complement,
`test_the_patient_is_told_who_they_are`, checks that the same profile does reach
the patient.

---

### `test_patient_profile.py` — 12 functions, 28 cases ✅

The score turns into behaviour, and what has no score is not invented. Three
blocks:

- **Band boundaries.** `_band_for` uses `score <= upper`, so a 2 is still the
  first band and a 2.1 is already the second. Both ladders are walked in full —
  2/4/6/8/10 for B-IPQ, 2/3/4/5 for BMQ — because they are different and
  confusing them would shift every patient by one band.
- **What is missing is omitted** (P9): a dimension with no number, a value that
  is not a number, and the whole medication block disappearing when the patient
  is on watch-and-wait (C1).
- **What the patient reads.** The clinical facts go through verbatim, but
  `test_the_score_itself_never_reaches_the_patient` checks that the number never
  appears: that is 1.9 in one line.

See also the band-floor rule in TASKS 7.1 — today a B-IPQ of 0 would be played as
a 2, and the corpus does not have one yet.

## Phase 3 — Report and arms

### `test_report.py` — 32 functions, 42 cases ✅

Five blocks, all of them with a reason:

- **The schema is the specification** (2.1) — `evidence` before `score`, and NA
  as a value.
- **Parsing** — an object with and without fences (GLM adds them even though
  REPORT.md asks it not to), anything else is `None` so the retry fires, and
  `test_a_score_off_the_scale_is_na_and_never_clamped`: the old arm did min/max
  and turned an illegal value into a legal-looking one.
  `test_the_two_scales_are_judged_separately` — 5.5 is legal in B-IPQ and illegal
  in BMQ.
- **What counts as unfinished** (1.13) — the fine distinction in `gaps()`: a
  declared NA **has reasoning and is an answer**; one the parser filled in does
  not, and that silence is the only thing asked about twice. `causes` is left out
  on purpose: demanding it is what produces an invented cause (N3).
- **Giving up instead of looping** — and
  `test_every_way_of_finishing_routes_to_the_report`, which is 1.13 entire: the
  report runs whoever closed the consultation.
- **Who writes it** — D9. The doctor continues its consultation, it does not read
  a transcript cold; it is sent the numbered transcript because `Evidence.turn`
  needs it; and it is asked without tools because there is nothing left to ask.

The two end-to-end tests sit behind `AHEAD_GRAPH_TESTS=1`.
`test_a_thin_report_is_asked_for_again_and_then_given_up_on` is **the only place
the retry path is exercised in full**. It had never fired live (N8, 24 runs with
`attempts: 1`) until 2026-09-01, when it fired and exhausted its attempts — see
N10.

### `test_coverage_hint.py` — 12 functions, 18 cases ✅

| Test | What it guards |
|---|---|
| `test_off_never_asks_the_doctor_anything` | The baseline does not have the argument |
| `test_show_asks_and_promises_what_comes_back` | — |
| `test_the_dimensions_it_names_are_taken` | — |
| `test_anything_it_does_not_declare_properly_is_simply_no_news` | Nothing about coverage may cost a call |
| `test_a_reply_with_no_call_declares_nothing` | — |
| `test_the_note_is_a_separate_message_in_our_own_voice` | It goes as `role: user`, the OPENING's channel, never inside a tool result |
| `test_there_is_no_note_when_nothing_is_open` | — |
| `test_the_map_accumulates_across_turns` | — |
| `test_show_hands_back_what_is_still_open` | — |
| `test_the_patient_never_sees_the_coverage_note` | In the patient's context it would be a list of topics |
| `test_the_doctor_can_always_close_with_dimensions_open` | All four modes: none of them compels covering anything (1.5) |
| `test_off_hands_back_nothing_at_all` | — |

### `test_notes.py` — 9 functions, 14 cases ✅

| Test | What it guards |
|---|---|
| `test_no_notes_argument_by_default` | — |
| `test_the_two_switches_are_independent` | All four combinations; in a single value there would be no telling which produced the effect |
| `test_a_note_is_taken_with_its_dimension` | — |
| `test_anything_malformed_is_discarded_and_the_call_survives` | Six malformed shapes |
| `test_a_note_carries_the_turn_it_was_taken_in` | — |
| `test_a_second_note_on_the_same_dimension_is_added_not_replaced` | **The one that justifies the arm**: a dated revision is the only thing that can show whether 1.11 buys anything |
| `test_nothing_is_recorded_when_the_arm_is_off` | The one that failed and revealed that `doctor_node` was not looking at the switch |
| `test_the_patient_never_sees_the_notes` | — |
| `test_the_transcript_keeps_only_what_was_said` | A note in the transcript is a sentence nobody spoke, and 3.2 verifies quotes against it |

---

## Phase 5 — Evaluation

### `test_evaluation.py` — 17 ✅

It separates **ported** from **new** explicitly, which is what makes the port
auditable. Ported: absolute error, signed bias, bands, MAE and median by hand.

New, and each against a concrete failure of the original:

- `test_an_na_is_excluded_from_the_mae_and_counted` — skipping it silently would
  give a report of 11 NAs a perfect MAE.
- `test_between_patient_has_nothing_to_say_when_everyone_gets_the_same_report` —
  **this is 2.5**: llama3.2's degenerate scorer (67% eights) had perfect spread
  and was useless.
- `test_ranking_survives_a_compressed_scale` — what `e4-1` shows: the order is
  right and the range is half. They are different problems and they are fixed
  differently (calibration, not more probing).
- `test_the_per_patient_mean_hides_what_the_per_dimension_bias_shows` — 4.5: Ruby
  reported +0.13 aggregate with `identity` at +1.00.
- `test_a_correlation_that_cannot_be_computed_is_none_not_zero` — the ported one
  returned 0.0, which reads as "no correlation" when it means "no data".

### `test_causes.py` — 17 ✅

Ported: cosine (including the zero vector, which would divide by zero), greedy
matching, threshold. New: `None` instead of 0.0 with no ground truth, `None`
instead of `"unknown"` for an unreadable answer — because `unknown` is a real
category for a patient who does not know — and **the recorded method**: the old
module changed metric silently when the embeddings failed, so a batch could mix
two measures without leaving a trace.

Two are pure regressions of the old parser:
`test_text_with_b_and_r_survives_intact` (it deleted every `b` and `r`: "Stress"
→ "St ess") and `test_markup_in_a_cause_is_left_alone`.

---

## Phase 6 — Coverage, fidelity and ablation

### `test_coverage.py` — 34 functions ✅

3.2 and 2.4. Synthetic fixtures: nothing here needs a batch on disk.

The `CONVERSATION` fixture is numbered as **exchanges**, not as interventions:
`nodes.py` gives the doctor's question and the patient's reply the same number
(D13). Reading it as four turns is the bug that cost a review — verifying a quote
requires crossing turn **and** role, because taking the first line with that
number lands on the doctor every time.

The six consistency tests (2.4) guard the distinction that separates 2.4 from
2.5: `test_a_gap_between_patients_does_not_inflate_the_within_patient_sd` puts
two patients at opposite ends of the scale, each perfectly stable, and requires a
consistency of 0. Pooling the scores before computing the sd would give a large
number, and it would be the distance between people — 2.5's question — disguised
as noise. `test_the_overall_consistency_is_none_when_nothing_reached_the_floor`
is the other side: below `MIN_REPEATS` the answer is "no data", never 0.0.

### `test_fidelity.py` — 38 functions, 50 cases ✅

3.5. **Half of this file is false positives**, and that is deliberate: a check
that shouts at normal speech gets ignored within a week, and then it checks
nothing.

- `test_a_denial_is_not_a_claim` — "I'm not taking anything" contains the same
  words as the assertion being looked for. Without the negation window the module
  would fire on exactly the sentences that **demonstrate** fidelity.
- `test_a_denial_early_in_the_turn_does_not_hide_a_claim_later_in_it` — the other
  side of the same thing. The negation stops reaching at `but`, `then` or a full
  stop: without that, "no nausea at first, but then the nausea got bad" reported
  nothing, because the search stopped at the first occurrence and that one was
  negated. A comma does **not** cut, so that "no pills, no tablets" stays one
  negation.
- `test_a_number_with_a_unit_after_it_is_not_an_age` — since a profile *without*
  an age also produces a finding, "I'm 45 minutes late" would fire on every
  patient instead of only on the ones that disagree. The unit guard is what makes
  that widening safe.
- `test_a_drug_claim_is_reported_once_not_twice` — "I'm taking ibrutinib" matches
  both the treatment rule and the drug rule. One claim is one finding, and the
  one that names the drug is kept.
- `test_the_quote_survives_doubled_whitespace` — the positions came from a copy
  with the whitespace collapsed, so any double space shifted the quote to the
  left of what it meant to show.
- `test_a_drug_in_the_turn_does_not_hide_the_symptoms` — **the one no other test
  could see.** A local variable in the drug loop shadowed the one holding the
  full text, so the symptom sweep searched inside the drug's name and any turn
  naming one came back with no symptoms. Each kind of finding was tested
  separately and the failure only appears when two coincide in the same turn.
- `test_ordinary_words_that_end_like_drugs_are_not_drugs` — the rule that catches
  `emtricitabine` also catches `medicine`, `routine` and `determine`. That is why
  the suffix stays at `-nib`/`-mab`/`-vir` and the rest is a named list.
- `test_a_drug_named_twice_is_one_finding` and the `headache`/`headaches`
  overlap: if a symptom is counted twice, the number of findings stops meaning
  anything.
- `test_the_belief_profile_is_never_read` — **the important one**. A patient
  expressing a belief is doing its job; checking beliefs here would penalise
  exactly the behaviour the simulation rests on.
- `test_the_doctors_lines_are_not_checked` — the doctor naming a drug is a
  question, not a fabrication by the patient.
- `test_the_scores_are_never_touched` — QC and nothing else: it reads
  `transcript.json` and does not open `report.json`.

### `test_ablation.py` — 17 functions ✅

5.4, only the deterministic part. `test_the_pieces_rebuild_the_text` is the
foundation: if splitting into sentences loses a character, the ablated transcript
stops being "the same text minus the evidence" and becomes a different text, at
which point the comparison between conditions does not measure the ablation.
**Whole sentences** are ablated on purpose — trimming inside the quote leaves a
mutilated turn, and the model would react to the mutilation as well as to the
missing evidence.

### `test_replay_server.py` — 20 functions, 20 cases ✅

The read layer of `replay_server.py`. **What is tested is the reading, not the
HTML**: which consultations a batch says it holds, whose they are, and what one
carries once read back off disk. Nothing needs a real batch — everything is
fabricated in `tmp_path`, so these say the same thing on a machine with an empty
`runs/`.

Four blocks:

**The disk decides, not the index.**
`test_the_disk_decides_what_exists_not_the_index` is the same invariant as
`coverage._index`: a batch resumed after a kill rewrites `batch.json` with *that*
launch's consultations, so trusting the index for what exists loses whole
sessions. The index *is* still read for `stop_reason`, which is nowhere else and
is the one thing the picker has to show — `turn_cap` is a result, not a fault.

**One patient at a time.**
`test_a_batch_holding_nobody_asked_for_disappears_entirely`: filtering the
consultations and leaving the batch would put an empty arm on screen, and an arm
with no consultations reads as an arm that failed. And both sides of the person
list: someone with a profile who never ran is not offered, and someone who ran
but lost their profile is — a transcript is worth reading even with nothing left
to score it against.

**What a consultation carries.** The report is **re-parsed** rather than taken on
trust, so the NA policy of 4.4 applies here too and an off-scale score comes back
NA instead of clamped. `test_the_evaluation_is_the_one_evaluate_py_would_give` is
the one that matters: the figure on screen has to be the one in
`evaluation.json`, and computing it a second way is how the two drift apart
without anyone noticing.

**Over HTTP.** A `..` in the URL does not read outside `runs/` — both parts are
used as directory names — and
`test_a_server_pinned_to_one_patient_cannot_be_talked_out_of_it`: `--patient` is
a decision about what that instance shows, not a default the browser can bypass
by asking for somebody else.

What it does **not** cover: the HTML. The turn by turn playback, the jump from a
quote to its turn and the drawing of NAs are seen by no test, the same way
`cover.py`'s formatting is not.

---

## What was removed, and why

Four tests retired in the cleanup. None of them stopped being checked: all four
were duplicated elsewhere. It is recorded here and not in the commit message
because a deleted test gets looked at months later, and this is where you look.

| Retired | Where it is still checked |
|---|---|
| `test_coverage.py::test_the_patient_channel_carries_only_the_patient` | `test_tools.py::test_the_patient_reply_goes_back_as_the_tool_result`, same assertion. The channel reasoning was carried over to it |
| `test_coverage.py::test_asking_the_doctor_does_not_disturb_the_tool_it_already_had` | Merged into `test_tools.py::test_building_the_tools_never_touches_the_one_the_module_ships`, now over all four modes |
| `test_notes.py::test_the_tool_the_module_ships_is_never_touched` | The same invariant, the same destination |
| `test_notes.py::test_the_doctor_still_closes_when_it_wants` | `test_coverage_hint.py::test_the_doctor_can_always_close_with_dimensions_open`, which went from 2 modes to all 4 combinations |
| `test_config.py::test_dimension_ids_match_every_patient` | `test_corpus.py::test_profile_carries_ground_truth` requires every dimension to be a number within range, and the value of a missing key is never read |

`test_coverage.py` was renamed **`test_coverage_hint.py`**. "Coverage" meant
three things at once: `causes.similarity.coverage_score` (ported), the
`coverage_hint` arm (this file) and the dimension × patient map of 3.2 (unwritten
at the time). 3.2 needed the name free.

---

## What is not covered

| Module | Status |
|---|---|
| `run_batch.py` | 0 tests. Its two guards (dirty tree, both temperatures at 0) are checked by nothing. Left that way for now |
| `main.py` | 0 tests |
| `cover.py`, `fidel.py`, `rescore.py` | 0 tests **of the CLI layer**. The modules underneath — `coverage.py`, `fidelity.py`, `ablation.py` — are covered; what is not checked is the formatting or the argument parsing. **What stands in for it is the `tools/make_dummy_batch.py` smoke test**, and it found three formatting failures no test would have seen |
| `tools/make_dummy_batch.py` | 0 tests, and **it is the only end-to-end exercise of `cover.py`**. It fabricates 2 patients × 5 repeats with the answer planted, so what it prints can be checked against what went in. It went from 3 to 5 repeats on 2026-08-31: with `MIN_REPEATS = 5` the 3-repeat version produced a batch with every SD null while its own text promised numbers, which is to say it had stopped exercising exactly what it exists to exercise |
| `ablation.rescore()` | 5.4's call to the model is not exercised: `test_ablation.py` covers the deterministic half — which sentence is removed, how the conditions are compared — and the rest would need the LLM scripted |
| `replay_frontend/index.html` | 0 tests. See `test_replay_server.py`: the read layer is covered, the browser layer is not |
| `api_server.py` (§8.9) | Does not exist |
| Skills §5.1 | The mechanism is tested; the test is waiting for a skill document to run it on |

`reproducibility.py` was deleted on 2026-08-27 and no longer appears here. What
2.4 needed was written inside `coverage.py`, with tests.
