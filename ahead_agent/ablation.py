# ahead_agent/ablation.py
# ─────────────────────────────────────────────
# 5.4 — ¿viene el número de la conversación, o del prior?
#
# Se quitan del transcript las frases que el propio médico citó como evidencia y
# se vuelve a puntuar. Si la puntuación no se mueve, la evidencia era decorativa
# y el número se decidió por otra vía.
#
# Dos condiciones, y las dos se puntúan de nuevo:
#
#   intact   el transcript entero, leído en frío
#   ablate   el mismo transcript sin las frases citadas, leído en frío
#
# `intact` no es un experimento aparte: es el **control**. El informe original lo
# escribió el médico continuando su propia consulta, con todos los turnos en su
# historial (D9); un lector en frío ve mucho menos. Comparar `ablate` contra el
# informe original mediría la ablación y la pérdida de contexto a la vez.
#
# Post-proceso: no importa nada de nodes ni de graph, así que corre sobre
# cualquier tanda ya escrita.
# ─────────────────────────────────────────────

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from . import llm, prompts
from . import report as report_module
from .coverage import DIMENSIONS, check_quote

INTACT = "intact"
ABLATE = "ablate"
MODES = (INTACT, ABLATE)


# ── Qué se quita ─────────────────────────────

# Se ablan **frases enteras**, no fragmentos. Recortar la cita por dentro deja
# un turno mutilado que ya no se lee como habla humana, y entonces el modelo
# reacciona a la mutilación además de a la falta de evidencia. Quitar de más es
# el lado seguro: si aun así el número no se mueve, la conclusión es más fuerte.
_SENTENCE = re.compile(r"[^.!?…]+[.!?…]*\s*")

_SPACE = re.compile(r"\s+")
_TYPOGRAPHY = str.maketrans(
    {"‘": "'", "’": "'", "“": '"', "”": '"', "–": "-", "—": "-", "…": "..."}
)


def _normalise(text: str) -> str:
    return _SPACE.sub(" ", text.translate(_TYPOGRAPHY)).strip().casefold()


def sentences(text: str) -> List[str]:
    """Trozos que, unidos, reconstruyen el texto."""
    return _SENTENCE.findall(text)


def cited_quotes(report, conversation: List[Dict[str, Any]]) -> Dict[int, List[str]]:
    """turno → citas que verifican en él.

    Sale de lo que el informe alega, no de buscar en el texto: cobertura ya
    comprobó cuáles existen de verdad y en qué turno. Una cita que no verifica
    no se abla — no está ahí para quitarla.
    """
    scored = {**report.bipq, **report.bmq}
    evidence = [e for dimension in scored.values() for e in dimension.evidence]
    evidence += list(report.causes_evidence)

    per_turn: Dict[int, List[str]] = {}
    for item in evidence:
        checked = check_quote(item, conversation)
        if checked.verified:
            per_turn.setdefault(checked.turn, []).append(item.quote)
    return per_turn


def ablate_turn(content: str, quotes: List[str]) -> str:
    """El turno sin las frases que solapan alguna cita."""
    needles = [_normalise(q) for q in quotes if q.strip()]

    kept = []
    for sentence in sentences(content):
        normalised = _normalise(sentence)
        # Solapa en cualquiera de los dos sentidos: la cita puede ser parte de
        # una frase larga, o abarcar varias frases cortas.
        overlaps = any(
            normalised and (normalised in needle or needle in normalised)
            for needle in needles
        )
        if not overlaps:
            kept.append(sentence)

    return "".join(kept).strip()


def ablate(conversation: List[Dict[str, Any]], per_turn: Dict[int, List[str]]) -> List[Dict[str, Any]]:
    """El transcript sin la evidencia alegada.

    **Los números de turno se conservan**, y un turno que se queda sin nada se
    queda vacío en vez de desaparecer: si se renumerara, el `Evidence.turn` del
    informe nuevo apuntaría a otro sitio y no se podría comparar con nada.
    Solo se toca al paciente: quitarle frases al médico cambiaría las preguntas,
    que es otro experimento.
    """
    ablated = []
    for line in conversation:
        quotes = per_turn.get(line.get("turn"), [])
        if line.get("role") == "patient" and quotes:
            line = {**line, "content": ablate_turn(line.get("content") or "", quotes)}
        ablated.append(line)
    return ablated


# ── Volver a puntuar, en frío ────────────────


@dataclass
class Rescore:
    run: str
    patient_id: str
    mode: str
    report: Optional[Any]
    raw: str
    removed_turns: int = 0
    removed_words: int = 0
    events: List[dict] = field(default_factory=list)


def rescore(config, conversation: List[Dict[str, Any]], patient_id: str, mode: str,
            removed: tuple = (0, 0)) -> Rescore:
    """Un informe nuevo sobre este transcript, sin más contexto que él.

    El lector en frío recibe las instrucciones de informe y la rúbrica —lo que
    hace falta para puntuar— y **no** el prompt de rol del médico ni el historial
    de la consulta. Idéntico en las dos condiciones, que es lo único que importa
    para que la diferencia sea la ablación.
    """
    events: List[dict] = []
    messages = [{
        "role": "user",
        "content": prompts.SEPARATOR.join([
            prompts.compose_prompt(config, "report"),
            report_module.transcript_text(conversation),
        ]),
    }]

    reply = llm.chat(config, "report", messages, events=events)
    raw = (reply.get("content") or "").strip()

    return Rescore(
        run="", patient_id=patient_id, mode=mode,
        report=report_module.parse(raw, patient_id), raw=raw,
        removed_turns=removed[0], removed_words=removed[1], events=events,
    )


def removal_size(before: List[Dict[str, Any]], after: List[Dict[str, Any]]) -> tuple:
    """Cuánto se quitó: turnos tocados y palabras. Va al resultado porque una
    ablación que no quitó nada no es una ablación, y sin esta cifra un `ablate`
    idéntico a `intact` se leería como un hallazgo."""
    turns = sum(
        1 for old, new in zip(before, after) if old.get("content") != new.get("content")
    )
    words = sum(
        len((old.get("content") or "").split()) - len((new.get("content") or "").split())
        for old, new in zip(before, after)
    )
    return turns, words


# ── Comparar las dos condiciones ─────────────


@dataclass
class Shift:
    """Una dimensión, de intact a ablate."""

    dimension: str
    intact: Optional[float]
    ablated: Optional[float]

    @property
    def moved(self) -> Optional[float]:
        if self.intact is None or self.ablated is None:
            return None
        return round(self.ablated - self.intact, 3)

    @property
    def lost(self) -> bool:
        """Tenía número y se quedó sin él: eso también es moverse."""
        return self.intact is not None and self.ablated is None


def shifts(intact, ablated) -> List[Shift]:
    """Dimensión a dimensión. `causes` no entra: no lleva número."""
    def score_of(parsed, name):
        if parsed is None:
            return None
        dimension = {**parsed.bipq, **parsed.bmq}.get(name)
        return dimension.score if dimension else None

    return [
        Shift(name, score_of(intact, name), score_of(ablated, name))
        for name in DIMENSIONS
        if name != "causes"
    ]
