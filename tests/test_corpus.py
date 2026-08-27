# tests/test_corpus.py
# Los 10 pacientes y su ground truth. Desde el 2026-08-26 el corpus es el de CK
# normalizado, no el que corrió el brazo Ruby: ver test_the_ruby_corpus_is_frozen.

import json
import re

import pytest

from ahead_agent import corpus
from ahead_agent.config import BIPQ_DIMENSIONS, BMQ_SUBSCALES, CAUSES_DIMENSION, REPO_ROOT

PATIENTS_DIR = REPO_ROOT / "patients"
CK_DIR = REPO_ROOT / "sintetic_patients" / "patientsCK"
PREVIOUS_DIR = REPO_ROOT / "sintetic_patients" / "patients_version1"
RUBY_PATIENTS_DIR = REPO_ROOT.parent / "modified_versions" / "ruby_version" / "patients"

PROFILES = sorted(PATIENTS_DIR.glob("*.json"))

FRACTION = re.compile(r"\d+/\d+")


def _quoted_ck(path):
    """Un fichero CK como dict. Los originales no son JSON válido —el BMQ va
    como `21/25` sin comillas—, así que se entrecomilla para poder parsearlo.
    Reimplementado aquí a propósito: el test no debe depender del script que
    generó lo que está comprobando."""
    return json.loads(re.sub(r":\s*(\d+)\s*/\s*(\d+)", r': "\1/\2"', path.read_text()))


def test_corpus_has_ten_patients():
    assert len(PROFILES) == 10


@pytest.mark.parametrize("path", PROFILES, ids=lambda p: p.stem)
def test_the_bmq_on_disk_is_the_original_fraction(path):
    """0.6 — el fichero guarda lo que dijo CK, no el resultado de convertirlo.
    Si aquí hubiera un float, el denominador —cuántos ítems tiene la subescala—
    se habría perdido y la conversión sería irreversible."""
    bmq = json.loads(path.read_text())["belief_profile"]["bmq"]

    for subscale in BMQ_SUBSCALES:
        assert isinstance(bmq[subscale], str), f"{subscale} ya viene convertido"
        assert FRACTION.fullmatch(bmq[subscale]), f"{subscale} = {bmq[subscale]}"


@pytest.mark.parametrize("path", PROFILES, ids=lambda p: p.stem)
def test_profile_carries_ground_truth(path):
    profile = corpus.load_patient(path)

    assert profile["patient_id"] == path.stem
    assert profile["disease_profile"]["diagnosis"]
    assert profile["disease_profile"]["demographics"]

    b_ipq = profile["belief_profile"]["b_ipq"]
    bmq = profile["belief_profile"]["bmq"]

    for dimension in BIPQ_DIMENSIONS:
        assert isinstance(b_ipq[dimension], (int, float)), dimension
        assert 0 <= b_ipq[dimension] <= 10, f"{dimension} fuera de la escala"

    # C1 retirado: el corpus CK puntúa las specific_* también sin receta, y esa
    # fue una decisión explícita al migrar. Antes se exigía None.
    for subscale in BMQ_SUBSCALES:
        assert isinstance(bmq[subscale], (int, float)), subscale
        assert 1 <= bmq[subscale] <= 5, f"{subscale} fuera de la escala 1-5"

    # causes vive dentro de b_ipq junto a los ocho números, pero es una lista de
    # cadenas: cualquiera que itere b_ipq y promedie se la encuentra de frente.
    assert isinstance(b_ipq[CAUSES_DIMENSION], list) and b_ipq[CAUSES_DIMENSION]


@pytest.mark.parametrize("path", PROFILES, ids=lambda p: p.stem)
def test_patients_is_the_ck_corpus_verbatim(path):
    """De dónde salió cada número. Desde 0.6 la única diferencia con el fichero
    de CK son las comillas de la fracción, que JSON exige; ningún valor cambia
    al escribir, así que la procedencia se comprueba comparando el contenido."""
    source = CK_DIR / f"{path.stem}_CK.json"

    assert source.exists(), f"{path.stem} no está en patientsCK"
    assert json.loads(path.read_text()) == _quoted_ck(source)


@pytest.mark.skipif(not RUBY_PATIENTS_DIR.exists(), reason="Ruby arm not present")
@pytest.mark.parametrize("path", sorted(PREVIOUS_DIR.glob("*.json")), ids=lambda p: p.stem)
def test_the_ruby_corpus_is_frozen(path):
    """Lo que 0.3 protegía. El corpus vivo ya no es el del brazo Ruby, pero las
    corridas de runs/historic/ se puntuaron contra este, así que reanalizarlas
    exige que siga intacto."""
    reference = RUBY_PATIENTS_DIR / path.name

    assert reference.exists(), f"{path.name} falta en el brazo Ruby"
    assert path.read_bytes() == reference.read_bytes()


# ── La normalización ─────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "raw, subscale, expected",
    [
        ("21/25", "specific_necessity", 4.2),   # 5 ítems
        ("25/25", "specific_concerns", 5.0),    # el techo de la escala
        ("5/25", "specific_necessity", 1.0),    # el suelo: cada ítem un 1
        ("7/20", "general_harm", 1.75),         # 4 ítems
        ("20/20", "general_overuse", 5.0),
    ],
)
def test_the_item_mean_returns_the_one_to_five_scale(raw, subscale, expected):
    """El denominador es el número de ítems por 5, no un divisor: 21/25 es una
    suma de 21 sobre 5 ítems, o sea 4.2, y nunca la proporción 0.84."""
    assert corpus.bmq_mean(raw, subscale) == expected


@pytest.mark.parametrize("raw", ["7/10", "21/24", "7/16"])
def test_an_unexpected_maximum_is_refused(raw):
    """Un máximo que no cuadra significa otro número de ítems, y normalizarlo
    igual mete un valor en otra escala sin que se note."""
    with pytest.raises(ValueError):
        corpus.bmq_mean(raw, "general_overuse")


def test_an_already_numeric_bmq_passes_through():
    """El corpus congelado de version1 guarda medias, no fracciones, y tiene que
    seguir cargando: la conversión se aplica a lo que viene como cadena."""
    profile = {"belief_profile": {"bmq": {"general_harm": 1.75, "general_overuse": None}}}

    assert corpus.normalize_beliefs(profile)["belief_profile"]["bmq"] == {
        "general_harm": 1.75, "general_overuse": None
    }


def test_the_loader_leaves_the_beliefs_alone():
    """Solo el BMQ cambia de forma. Si tocara el b_ipq, el ground truth de ocho
    dimensiones dependería del cargador sin que nadie lo hubiera decidido."""
    for path in PROFILES:
        source = (CK_DIR / f"{path.stem}_CK.json").read_text()
        b_ipq = corpus.load_patient(path)["belief_profile"]["b_ipq"]
        for dimension in BIPQ_DIMENSIONS:
            assert f'"{dimension}": {b_ipq[dimension]}' in source, f"{path.stem}/{dimension}"
