# Inherited failures

Concrete failures from the earlier arms, with where they were seen and where
they stand here. It serves two purposes: not repeating them, and being able to
say exactly what changed when one is fixed.

Status: **RESOLVED** · **OPEN** · **PENDING** (it belongs to a later phase).

---

## Python arm (elicitation)

| # | Problem | Status |
|---|---|---|
| P1 | **A default value instead of NA.** The scorer put in a 5 (3.0 for BMQ) when the JSON did not parse, and if that failed too it took the first number in the text. Invented values that then counted as hits (4.4). | RESOLVED — `report.parse` leaves NA on absence, wrong type or out-of-scale value, and **never clamps**. Verified on s3-1 and s3-2: three `null`s with empty evidence, none filled in |
| P2 | **Re-asking by length.** The routing fired on `len(reply) < 10 words`, so a long vague answer went straight to scoring (1.12). | RESOLVED — there is no length rule in the code; `DOCTOR.md` says *"thin is about content, not length"* |
| P3 | **Walking a list of questions.** `q_index`, `bmq_index` and `follow_up_count` set the pace: the questionnaire was the script. | RESOLVED — out of `State`; the doctor decides through a tool call |
| P4 | **Degenerate scorer.** llama3.2 answered 8 sixty-seven percent of the time. Maximum consistency, zero discrimination (2.5). | OPEN — **it comes back with GLM**: s3-1 scored 6 on all eight B-IPQ dimensions (MAE 3.25). s3-2, same configuration, spread itself over 2/4/6 (MAE 2.00). Measured in Stage 6 by 2.4 and 2.5 together |
| P5 | **Asymmetric per-dimension bias**: `identity` +1.00, `consequences` +0.97, `treatment_control` −0.77, `personal_control` −0.63. The aggregate (+0.13) hid it (4.5). | PENDING — Stage 5, `evaluation.py` per dimension |
| P6 | **Causes parser built on an improvised regex**: it deleted every `b` and `r` in the text ("Stress" → "St ess") (4.3). | PENDING — Stage 5, when `causes/` is ported |
| P7 | **Ground truth taken from an earlier run** labelled `reference`. That measures drift between runs, not accuracy (4.1). | RESOLVED — `write_transcript` does not copy the `belief_profile`; ground truth is read from `patients/*.json` |
| P8 | **A single `CONFIG["model"]`** for doctor and scorer: there was no way to know who used what. | RESOLVED — `models.doctor` / `models.patient`, and a temperature per role |
| P9 | **A default score inside the patient prompt**: `bp.get(dim, 5)` invented a 5 for the dimensions that were missing. | RESOLVED — `_cues` omits a missing dimension, never fills it |
| P10 | **The doctor could not see the conversation.** Each question was sent as `[system, instruction]`, with no history: it could not infer from what came before. | RESOLVED — `doctor_messages` accumulates and is resent whole |

## Ruby arm (inference)

| # | Problem | Status |
|---|---|---|
| R1 | **One doctor agent for every patient**, created outside the loop and reset with `doctor.start`. If the reset was not complete, patient N saw traces of N−1. | RESOLVED — `State` is created per consultation; the test for two consecutive consultations is still missing |
| R2 | **An unvalidated report.** The trigger was a loose phrase and the result was stored as it came: that is how CLL-004's report was lost (1.13). | PENDING — Stage 3, validation and retry |
| R3 | **`Score \| Rationale`**: the justification was generated after the number, so it was decorative (2.1). | HALF RESOLVED — `DimensionScore` fixes the order `evidence → reasoning → score` and there is a test on the fields. That the order is respected does not prove the number follows the evidence: that is what [N3] decides |
| R4 | **A mirrored rubric.** `DOCTOR.md` said what to listen for and `PATIENT.md` how to express it: the same table on both sides. Part of the accuracy was decoding a code of our own (5.5). | RESOLVED in the v2 prompts — the doctor is given what each dimension captures, not which signal corresponds to which level |
| R5 | **Only 0 and 10 anchored** on the scale: any evidence pushes to an extreme (2.2). | HALF RESOLVED — `prompts/doctor_rubric/*.json` anchors 2/4/6/8 from clinical criteria. In s3-2 the doctor used 2, 4 and 6 but **never 8**, with a truth of 8 and 9 on two dimensions: the top of the range is still out of reach |
| R6 | **Empty turns (~19%) and failed reports (~26%)** with no retry (3.1). | RESOLVED — `llm.py` retries transport and empty replies, and records it in `events` |
| R7 | **`salloc` without `srun`** in `submit.sh`: the job ran on the login node, which on ACC also has H100s, so nobody noticed (§6.3). | HALF RESOLVED — `metadata.compute` stores `hostname` and `slurm_nodelist` to detect it; the launcher is still missing |
| R8 | **Implicit temperature.** Gepeto applies 0.7 when none is sent, and is stochastic even at 0 (§12). | RESOLVED — temperature and `num_ctx` are always sent and always recorded |
| R9 | **`OLLAMA_CONTEXT_LENGTH` and `keep_alive` as server variables**: invisible from the client and absent from the metadata. | RESOLVED — they travel in every request, from the profile |

## Corpus (both arms share the same 10 profiles)

| # | Problem | Status |
|---|---|---|
| C1 | **Patients on no medication with a BMQ *specific* score.** The *specific* subscales are defined over the prescribed drug: with no prescription there is no belief to measure. | OPEN and **confirmed in flight** — 3 of 10: CLL-001 (3.4/2.8), CLL-003 (2.0/1.5), CLL-005 (3.6/3.0). In s3-1 `describe()` gave CLL-003 hints about its medication, the patient invented a prescription (*"why I need to be taking specific medications"*) and the doctor scored `specific_concerns` 3.0 over a drug that does not exist. The fix: `null` in both *specific* subscales of those three. **And it shows up inverted in s3-3**: the report gave NA to `specific_necessity`, `general_harm` and `general_overuse` for CLL-003, which is correct, while the ground truth says 2.0/1.8/2.0. Evaluated today they would count as the doctor's mistakes |
| C2 | **`causes` lives inside `b_ipq`**, next to eight numbers and being a list of strings. Any code that iterates and averages swallows it. | RESOLVED — `BIPQ_DIMENSIONS` excludes it; there is a per-dimension type test |
| C3 | **Incomplete coverage in the conversation**: the doctor does not reach some dimensions. | OPEN — in s3-1 and s3-2 (12 and 11 turns, closed by the doctor) **`causes`, `general_harm` and `general_overuse` were never mentioned once**, and the report scored them or made them up anyway. `DOCTOR.md` already warns (*"If you never ask, you will never know"*) and it is not enough: in the Ruby arm, probe table included, it was 0/10 on those same dimensions. What fixes it is `coverage_hint` (§4.1), not more prose |

## Findings from the new arm

Not inherited: they come out of the Stage 3 runs.

| # | Problem | Status |
|---|---|---|
| N1 | **The patient does not interpret its profile.** CLL-003 has `consequences` 2, `concern` 2, `emotional_response` 1 and `coherence` 9 — someone calm, barely affected and well informed. In s3-1 it said *"we're both quite worried"*, *"really unnerving"* and *"struggling even to do those things"*, and broke the clinical facts on top: *"carrying this condition over the years"* with a diagnosis six months old. The doctor scored well what it heard; what it heard was a different patient. | OPEN — §6.2 already marks `dolphin-llama3` as PROVISIONAL and unverified. A fidelity probe is needed before touching anything downstream: while this fails, any MAE measures the patient's infidelity, not the doctor's inference |
| N2 | **The spread between runs buries any improvement.** Four runs, same configuration and same prompt: CLL-003 gave MAE 3.25, 2.00 and 2.75. The report is generated at temperature 0, so all of that difference comes from the conversation (0.7). | OPEN — no measurable intervention is larger than that noise. `run_batch.py` (§2, PORT) is needed before evaluating a single change of prompt or anchor |
| N3 | **Causes that are not causes.** In four runs the doctor never asked about causes, and returned something anyway. First circular (*"history with CLL"*, *"CLL diagnosis"*), then the **disease mechanism** (*"affecting my body's immune system cells"*, *"chronic condition affecting my immune system"*). HIV-002's truth is behavioural — *"unprotected sex"*, *"being too trusting of a partner"* — and looks nothing like it. With `coverage_hint: "off"`, not asking is the expected result; answering anyway is not. | OPEN — validation (1.13) can cut this without a model: a cause with no `causes_evidence` behind it is not a cause |
| N4 | **The model fences the JSON.** `REPORT.md` asks for an object and nothing else, with no code fences; GLM wraps it in ```` ```json ```` regardless. | RESOLVED — `report.parse` strips them before parsing, and there is a regression test with the real shape |
| N5 | **The model picks a register per run, not a score per dimension.** s3-1 `6,6,6,6,6,6,6,6`; s3-2 `2,6,4,4,2,4,6,4`; s3-3 `6,8,8,6,6,4,8,6`; s3-4 `8,8,6,8,8,8,8,8`. Within each run it moves little; what shifts between runs is the centre. This is not per-dimension noise: it decides early "what kind of patient this is" and scores around that impression. It is P4 in a form harder to see than llama3.2's 67% of eights. | OPEN — measured by 2.5 (discrimination) alongside 2.4 (spread), never by the MAE alone |
| N6 | **The MAE can mislead.** s3-4 is the best of the four (1.75) with seven eights out of eight: it was right because HIV-002 is a high patient and it happened to land on a high register. Inside that same report, `identity` truth 3 and report 8 — an error of 5. | OPEN — do not publish an MAE without discrimination beside it (2.5) |
| N7 | **Declared confidence does not calibrate.** s3-3 `emotional_response` truth 1, report 6, confidence 0.8; `timeline` truth 3, report 8, confidence 0.9. High confidence does not predict accuracy, so today it cannot be used to filter. It *is* honest on the NAs: `general_harm` at 0.0 in s3-4. | OPEN — crossed with the observed spread in Stage 6 (2.3 + 2.4) |
| N8 | **The report retry has never fired.** Four runs, `attempts: 1` every time: all twelve dimensions come back with a justification. The tests cover that it works; there is no evidence yet that it is needed. | **CLOSED on 2026-09-01** — it fired and exhausted its attempts in 2 of 40 consultations. N10 replaces it |
| N9 | **1.12 is left open on purpose.** Stage 3 closes with `coverage_hint: "off"`, so ambiguity-driven probing has no mechanism: the doctor probes what it wants and coverage is audited afterwards (3.2). A deliberate decision — forcing coverage inflates the result and turns the consultation into a questionnaire. | DECIDED — the three arms (`off` / `declare` / `show`) exist and are compared in Stage 8 |
| N10 | **The empty-reply retry could not work on the report.** `llm.py` built the request body **outside** the loop, so all three attempts sent identical bytes; and `report_temperature` is 0.0. An identical request plus temperature zero is the same empty reply three times: the retry spent three attempts and six seconds reproducing the failure. For doctor and patient (T=0.7) a redraw can differ, and against a transport failure repeating is correct — what did not work is the combination "empty reply" + "T=0", which is exactly the report's. Measured cost: 2 consultations out of 40, and with them the SDs of two whole batches. Why the first came back empty **is not known**: the exception rises before `write_transcript`, so those consultations left nothing to inspect. | **RESOLVED on 2026-09-01.** `RESAMPLE_FLOOR = (0.3, 0.6)`: each empty reply raises the temperature floor of the next attempt, and it **only raises** — a role already sampling above the floor is left alone. The body is rebuilt per attempt, because it stops being constant once the reply has to come back different. The distinction is what matters: **a transport failure repeats the identical request** (the server did not answer) and **an empty reply changes the draw** (the model answered nothing). A pinned seed moves too, `seed + empties`, or the draw would be identical despite the temperature. The clash with §12 is resolved without giving ground: `metadata.sampling` still records the declared temperature, which is attempt 1's, and the retry's goes into the event as `retry_temperature`. Five new tests in `test_llm.py` |
