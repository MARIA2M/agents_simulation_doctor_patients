# tests/test_ablation.py
# 5.4 — quitar la evidencia alegada y volver a puntuar. Aquí solo la parte
# determinista: qué se quita y cómo se compara. La llamada al modelo no se toca.

import json

import pytest

from ahead_agent import ablation
from ahead_agent.report import Evidence

from test_coverage import CONVERSATION, DOSE, SHIFT, quote, report_body


def parsed(**dimensions):
    from ahead_agent import report as report_module

    return report_module.parse(json.dumps(report_body(**dimensions)), "TEST-001")


# ── Trocear ──────────────────────────────────


@pytest.mark.parametrize(
    "text",
    ["One. Two! Three?", "Sin puntuación final", "  Espacios.  Y más.  ", ""],
    ids=["tres frases", "sin punto", "espacios", "vacío"],
)
def test_the_pieces_rebuild_the_text(text):
    """Si trocear pierde un carácter, el transcript ablado deja de ser el mismo
    texto menos la evidencia y pasa a ser otro texto."""
    assert "".join(ablation.sentences(text)) == text


# ── Qué se quita ─────────────────────────────


def test_the_sentence_that_carries_the_quote_goes():
    turn = "I can barely get through a shift any more. The tiredness is constant."

    assert ablation.ablate_turn(turn, [SHIFT]) == "The tiredness is constant."


def test_the_rest_of_the_turn_stays():
    """Se abla la evidencia, no el turno: lo que no se citó sigue ahí porque
    quitarlo mediría otra cosa."""
    turn = "I sleep badly. I can barely get through a shift any more. My wife worries."

    assert ablation.ablate_turn(turn, [SHIFT]) == "I sleep badly. My wife worries."


def test_a_quote_spanning_several_sentences_takes_all_of_them():
    turn = "I sleep badly. It is constant. And it wears me down."

    assert ablation.ablate_turn(turn, ["It is constant. And it wears me down."]) == "I sleep badly."


def test_a_quote_that_is_not_there_removes_nothing():
    turn = "I sleep badly."

    assert ablation.ablate_turn(turn, ["something nobody said"]) == turn


# ── Sobre la conversación ────────────────────


def cited(*evidence):
    return {turn: [q for q, t in evidence if t == turn] for _, turn in evidence}


def test_only_the_patient_is_ablated():
    """Quitarle frases al médico cambiaría las preguntas, que es otro
    experimento. Aquí la cita es literalmente la línea del médico y aun así se
    queda: la regla es del hablante, no del texto."""
    per_turn = {2: ["And the tablets?", DOSE]}

    ablated = ablation.ablate(CONVERSATION, per_turn)
    doctor = next(l for l in ablated if l["turn"] == 2 and l["role"] == "doctor")
    patient = next(l for l in ablated if l["turn"] == 2 and l["role"] == "patient")

    assert doctor["content"] == "And the tablets?"      # intacta
    assert DOSE not in patient["content"]               # y la del paciente, fuera


def test_turn_numbers_survive():
    """Si se renumerara, el Evidence.turn del informe nuevo apuntaría a otro
    sitio y las dos condiciones dejarían de ser comparables."""
    ablated = ablation.ablate(CONVERSATION, {1: [SHIFT]})

    assert [l["turn"] for l in ablated] == [l["turn"] for l in CONVERSATION]
    assert len(ablated) == len(CONVERSATION)


def test_a_turn_emptied_completely_stays_as_an_empty_turn():
    ablated = ablation.ablate(CONVERSATION, {1: [SHIFT]})
    patient = next(l for l in ablated if l["turn"] == 1 and l["role"] == "patient")

    assert patient["content"] == ""


def test_only_verified_quotes_are_removed():
    """Una cita que no existe en el transcript no está ahí para quitarla, y
    contarla como ablada inflaría lo que creemos haber quitado."""
    report = parsed(consequences=([quote(SHIFT, 1), quote("nunca dicho", 1)], 8))

    assert ablation.cited_quotes(report, CONVERSATION) == {1: [SHIFT]}


def test_the_quotes_of_every_dimension_are_collected():
    report = parsed(consequences=([quote(SHIFT, 1)], 8),
                    specific_necessity=([quote(DOSE, 2)], 4.5))

    assert ablation.cited_quotes(report, CONVERSATION) == {1: [SHIFT], 2: [DOSE]}


# ── Cuánto se quitó ──────────────────────────


def test_the_size_of_the_removal_is_reported():
    """Una ablación que no quitó nada no es una ablación, y sin esta cifra un
    resultado idéntico se leería como hallazgo en vez de como fallo."""
    ablated = ablation.ablate(CONVERSATION, {1: [SHIFT]})
    turns, words = ablation.removal_size(CONVERSATION, ablated)

    assert turns == 1
    assert words == len(SHIFT.split())


def test_removing_nothing_is_visible():
    assert ablation.removal_size(CONVERSATION, CONVERSATION) == (0, 0)


# ── La comparación ───────────────────────────


def test_a_score_that_does_not_move():
    moved = ablation.shifts(parsed(consequences=([], 8)), parsed(consequences=([], 8)))
    consequences = next(s for s in moved if s.dimension == "consequences")

    assert consequences.moved == 0.0
    assert not consequences.lost


def test_a_score_that_moves_keeps_its_sign():
    moved = ablation.shifts(parsed(consequences=([], 8)), parsed(consequences=([], 5)))

    assert next(s for s in moved if s.dimension == "consequences").moved == -3.0


def test_losing_the_number_is_also_moving():
    """Sin evidencia, la política NA dice que no hay número. Eso es un efecto de
    la ablación, no un dato que falte."""
    moved = ablation.shifts(parsed(consequences=([], 8)), parsed(consequences=([], None)))
    consequences = next(s for s in moved if s.dimension == "consequences")

    assert consequences.moved is None
    assert consequences.lost


def test_causes_is_out_of_the_comparison():
    """No lleva número, así que no puede desplazarse."""
    assert not [s for s in ablation.shifts(parsed(), parsed()) if s.dimension == "causes"]


# ── El invariante ────────────────────────────


def test_ablation_is_post_process_only():
    import ast
    from pathlib import Path

    source = Path(ablation.__file__).read_text()
    imported = {
        node.module
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.ImportFrom) and node.module
    }

    assert not {"nodes", "graph"} & imported
