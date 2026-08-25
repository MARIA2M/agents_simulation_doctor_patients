# tests/test_evaluation.py
# Métricas contra valores calculados a mano (§8, Etapa 5).
# What was ported is checked as-is; what is new — NA and aggregation — apart.

import json

import pytest

from ahead_agent import evaluation, report


def scored(**dimensions):
    """A Report with only the dimensions named; the rest come back NA."""
    body = {"bipq": {}, "bmq": {}}
    for name, value in dimensions.items():
        block = "bipq" if name in evaluation.BIPQ_DIMENSIONS else "bmq"
        body[block][name] = {"evidence": [], "reasoning": "said so", "score": value}
    return report.parse(json.dumps(body), "TEST-001")


def truth(**values):
    b_ipq = {k: v for k, v in values.items() if k in evaluation.BIPQ_DIMENSIONS}
    bmq = {k: v for k, v in values.items() if k in evaluation.BMQ_SUBSCALES}
    return {"b_ipq": b_ipq, "bmq": bmq}


# ── PORTADO: the per-dimension arithmetic ────


def test_absolute_error_and_bias():
    """Bias keeps its sign: positive means the doctor scored above the truth."""
    m = evaluation.evaluate_patient(scored(consequences=8), truth(consequences=2))
    consequences = m.dimensions[0]

    assert consequences.absolute_error == 6.0
    assert consequences.bias == 6.0


def test_bias_is_negative_when_it_underscores():
    m = evaluation.evaluate_patient(scored(coherence=6), truth(coherence=9))

    assert next(d for d in m.dimensions if d.dimension == "coherence").bias == -3.0


def test_the_bands_are_the_ones_the_task_names():
    """within_1/within_2 for B-IPQ, within_half/within_one for BMQ (4.2)."""
    m = evaluation.evaluate_patient(
        scored(concern=3, general_harm=2.4), truth(concern=2, general_harm=2.0)
    )

    concern = next(d for d in m.dimensions if d.dimension == "concern")
    harm = next(d for d in m.dimensions if d.dimension == "general_harm")

    assert concern.bands == {"within_1": True, "within_2": True}
    assert harm.bands == {"within_half": True, "within_one": True}


def test_mae_and_median_by_hand():
    """Errors 4, 0 and 2 → MAE 2.0, median 2.0."""
    m = evaluation.evaluate_patient(
        scored(consequences=6, timeline=3, identity=4),
        truth(consequences=2, timeline=3, identity=2),
    )

    assert m.mae == 2.0
    assert m.median_ae == 2.0
    assert m.exact_matches == 1


# ── NUEVO: NA is a value, not a missing key (4.4) ──


def test_an_na_is_excluded_from_the_mae_and_counted():
    """Skipping it silently would give a report of 11 NAs a perfect MAE."""
    m = evaluation.evaluate_patient(
        scored(consequences=4, timeline=None), truth(consequences=2, timeline=3)
    )

    assert m.mae == 2.0                      # solo consequences
    assert m.scored == 1 and m.na == 11
    assert m.coverage_rate == round(1 / 12, 3)


def test_a_truth_that_is_missing_is_also_na():
    """C1: a watch-and-wait patient has no belief about a drug they do not take.
    Scoring it as an error would punish the doctor for being right."""
    m = evaluation.evaluate_patient(scored(specific_necessity=None), truth())

    assert m.scored == 0
    assert m.mae is None


def test_a_perfect_report_of_nothing_is_not_perfect():
    m = evaluation.evaluate_patient(scored(), truth(consequences=2))

    assert m.mae is None and m.coverage_rate == 0.0


# ── NUEVO: the two correlations never share a name ──


def test_within_patient_follows_the_shape_of_one_profile():
    """Every score two points high: the values are wrong, the shape is exact."""
    m = evaluation.evaluate_patient(
        scored(consequences=4, timeline=5, personal_control=10, coherence=6),
        truth(consequences=2, timeline=3, personal_control=8, coherence=4),
    )

    assert m.within_patient_r == 1.0
    assert m.mae == 2.0


def test_between_patient_has_nothing_to_say_when_everyone_gets_the_same_report():
    """The failure 2.5 exists to catch: a scorer that repeats one patient can
    still post a respectable MAE. With no spread of its own there is no
    correlation to compute, and None says that — 0.0 would read as a finding."""
    same = scored(consequences=5, timeline=5)
    batch = [
        (same, truth(consequences=2, timeline=2)),
        (same, truth(consequences=5, timeline=5)),
        (same, truth(consequences=8, timeline=8)),
    ]

    assert evaluation.evaluate_batch(batch).between_patient_r is None


def test_between_patient_is_one_when_it_ranks_them_perfectly():
    batch = [
        (scored(consequences=2), truth(consequences=2)),
        (scored(consequences=5), truth(consequences=5)),
        (scored(consequences=8), truth(consequences=8)),
    ]

    assert evaluation.evaluate_batch(batch).between_patient_r == 1.0


def test_ranking_survives_a_compressed_scale():
    """What e4-1 shows: the order is right and the range is halved. The
    correlation stays high, which is why it is reported next to the bias."""
    batch = [
        (scored(consequences=4), truth(consequences=2)),
        (scored(consequences=5), truth(consequences=5)),
        (scored(consequences=6), truth(consequences=8)),
    ]

    assert evaluation.evaluate_batch(batch).between_patient_r == 1.0


# ── NUEVO: aggregate per dimension, not per patient (4.5) ──


def test_the_per_patient_mean_hides_what_the_per_dimension_bias_shows():
    """Ruby reported +0.13 aggregate while identity sat at +1.00 and
    treatment_control at −0.77. Averaging the two is how it disappeared."""
    one = (scored(identity=6, treatment_control=2), truth(identity=2, treatment_control=6))
    batch = evaluation.evaluate_batch([one])

    assert batch.patients[0].mean_bias == 0.0          # +4 y −4 se cancelan
    assert batch.by_dimension["identity"].bias == 4.0
    assert batch.by_dimension["treatment_control"].bias == -4.0


def test_coverage_is_reported_per_dimension():
    """Which dimension goes unanswered, and how often — the input to 3.2."""
    batch = evaluation.evaluate_batch(
        [
            (scored(general_overuse=None), truth(general_overuse=2.0)),
            (scored(general_overuse=3.0), truth(general_overuse=2.0)),
        ]
    )

    overuse = batch.by_dimension["general_overuse"]
    assert overuse.scored == 1 and overuse.na == 1
    assert overuse.coverage_rate == 0.5


# ── With no data, no number is invented ──────


def test_a_correlation_that_cannot_be_computed_is_none_not_zero():
    """The ported version returned 0.0, which reads as "no correlation" when it
    means "not enough data" — the confusion NA exists to prevent."""
    assert evaluation._pearson([1.0], [2.0]) is None
    assert evaluation._pearson([3.0, 3.0, 3.0], [1.0, 2.0, 3.0]) is None
