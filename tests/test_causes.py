# tests/test_causes.py
# El módulo de causas (4.3). Sin servidor: el clasificador y los embeddings
# están sustituidos. Incluye la regresión del parser viejo, que borraba toda
# `b` y `r` del texto ("Stress" → "St ess").

import math

import pytest

from ahead_agent import causes
from ahead_agent.causes import scorer, similarity, taxonomy
from ahead_agent.causes.types import CausesScore, ClassifiedCause

CONFIG = {
    "models": {"doctor": "doc", "patient": "pat", "embed": "emb"},
    "sampling": {"doctor_temperature": 0.7, "patient_temperature": 0.7,
                 "report_temperature": 0.0, "seed": None, "context_length": 32768},
    "server": {"ollama_url": "http://127.0.0.1:11434", "request_timeout": 300,
               "keep_alive": "1h"},
}


@pytest.fixture
def classifier(monkeypatch):
    """The classifier answers whatever the test queued for that text."""
    answers = {}

    def fake_chat(config, role, messages, tools=None, events=None, usage=None):
        prompt = messages[0]["content"]
        for text, category in answers.items():
            if f'"{text}"' in prompt:
                return {"content": category}
        return {"content": "unknown"}

    monkeypatch.setattr(scorer.llm, "chat", fake_chat)
    return answers


@pytest.fixture
def vectors(monkeypatch):
    """Deterministic embeddings: each text gets the vector it is assigned."""
    table = {}

    monkeypatch.setattr(scorer, "embedding_model_available", lambda config: True)
    monkeypatch.setattr(
        scorer, "get_embeddings", lambda config, texts: [table[t] for t in texts]
    )
    return table


# ── PORTADO: cosine and matching ─────────────


def test_cosine_of_identical_vectors_is_one():
    assert similarity.cosine_similarity([1.0, 0.0], [1.0, 0.0]) == 1.0


def test_cosine_of_orthogonal_vectors_is_zero():
    assert similarity.cosine_similarity([1.0, 0.0], [0.0, 1.0]) == 0.0


def test_a_zero_vector_does_not_divide_by_zero():
    assert similarity.cosine_similarity([0.0, 0.0], [1.0, 1.0]) == 0.0


def test_each_inferred_cause_is_matched_at_most_once():
    """Greedy in order of importance: the first true cause takes the best one."""
    truth = [ClassifiedCause("genetics", "biological"),
             ClassifiedCause("family history", "biological")]
    inferred = [ClassifiedCause("my father had it", "biological")]
    matrix = [[0.9], [0.8]]

    matches, unmatched = similarity.greedy_match(truth, inferred, matrix)

    assert matches[0].inferred.text == "my father had it"
    assert matches[1].inferred is None and matches[1].similarity == 0.0
    assert unmatched == []


def test_below_the_threshold_is_a_pairing_but_not_a_match():
    """The pairing is kept so it can be inspected; it just does not count as a hit."""
    truth = [ClassifiedCause("stress at work", "psychological")]
    inferred = [ClassifiedCause("the weather", "social")]

    matches, _ = similarity.greedy_match(truth, inferred, [[0.30]])

    assert matches[0].inferred is not None
    assert matches[0].matched is False
    assert similarity.coverage_score(matches) == 0.0


# ── NUEVO: with no data, no number is invented ──


def test_coverage_without_ground_truth_is_none_not_zero():
    """0.0 would read as "it found none", which is a result."""
    assert similarity.coverage_score([]) is None
    assert similarity.mean_similarity([]) is None


# ── NUEVO: an unreadable category is not "unknown" ──


def test_a_category_the_model_names_is_read():
    assert taxonomy.parse_category("behavioural") == "behavioural"
    assert taxonomy.parse_category("  Biological.  ") == "biological"


def test_an_unreadable_answer_is_none():
    """The original returned "unknown", which means *the patient does not know* —
    a clinical finding. A parsing failure is not one."""
    assert taxonomy.parse_category("I am not sure how to classify this") is None
    assert taxonomy.parse_category("") is None


def test_the_patient_not_knowing_is_still_a_real_category():
    assert taxonomy.parse_category("unknown") == "unknown"


# ── NUEVO: the method used is recorded ───────


def test_embeddings_are_used_and_named(classifier, vectors):
    classifier.update({"genetics": "biological", "my father had it": "biological"})
    vectors.update({"genetics": [1.0, 0.0], "my father had it": [0.99, 0.14]})

    score = causes.score_causes(CONFIG, ["my father had it"], ["genetics"])

    assert score.method == "embeddings"
    assert score.coverage_score == 1.0
    assert score.threshold == similarity.MATCH_THRESHOLD


def test_falling_back_to_categories_says_so(classifier, monkeypatch):
    """The old module switched metric silently, so one batch could carry
    `coverage_score` computed two different ways."""
    monkeypatch.setattr(scorer, "embedding_model_available", lambda config: False)
    classifier.update({"genetics": "biological", "my father had it": "biological"})

    score = causes.score_causes(CONFIG, ["my father had it"], ["genetics"])

    assert score.method == "categories"
    assert score.coverage_score == 1.0          # misma categoría, mucho más grueso
    assert score.mean_similarity is None
    assert any(e["event"] == "embeddings_unavailable" for e in score.events)


def test_an_embedding_failure_is_recorded_not_swallowed(classifier, monkeypatch):
    def explode(config, texts):
        raise scorer.EmbeddingError("connection refused")

    monkeypatch.setattr(scorer, "embedding_model_available", lambda config: True)
    monkeypatch.setattr(scorer, "get_embeddings", explode)
    classifier.update({"genetics": "biological"})

    score = causes.score_causes(CONFIG, ["my father had it"], ["genetics"])

    assert score.method == "categories"
    assert any(e["event"] == "embeddings_failed" for e in score.events)


# ── Regression of the old parser (4.3) ───────


def test_text_with_b_and_r_survives_intact(classifier, vectors):
    """The old parser stripped every `b` and `r`: "Stress" came out "St ess"."""
    classifier.update({"Stress from work": "psychological",
                       "Being too trusting of a partner": "social"})
    vectors.update({"Stress from work": [1.0, 0.0],
                    "Being too trusting of a partner": [1.0, 0.0]})

    score = causes.score_causes(
        CONFIG, ["Being too trusting of a partner"], ["Stress from work"]
    )

    assert score.inferred_causes[0].text == "Being too trusting of a partner"
    assert score.ground_truth_causes[0].text == "Stress from work"


def test_markup_in_a_cause_is_left_alone(classifier, vectors):
    """The Ruby arm's causes carried `<br/>` and asterisks."""
    text = "Genetics <br/> **family history**"
    classifier.update({text: "biological"})
    vectors.update({text: [1.0, 0.0]})

    score = causes.score_causes(CONFIG, [text])

    assert score.inferred_causes[0].text == text


# ── Diversity and empty lists ────────────────


def test_diversity_counts_distinct_categories_over_the_taxonomy(classifier, vectors):
    classifier.update({"genetics": "biological", "stress": "psychological"})

    score = causes.score_causes(CONFIG, ["genetics", "stress"])

    assert score.category_diversity == round(2 / len(causes.CAUSE_CATEGORIES), 3)


def test_no_causes_at_all_is_none_not_zero(classifier):
    """A doctor who never asked returns an empty list, and that is not zero
    diversity: it is absence of data."""
    score = causes.score_causes(CONFIG, [])

    assert score.inferred_causes == []
    assert score.category_diversity is None
    assert score.coverage_score is None


def test_empty_strings_are_dropped_before_classifying(classifier):
    score = causes.score_causes(CONFIG, ["", None, "   "])

    assert score.inferred_causes == []
