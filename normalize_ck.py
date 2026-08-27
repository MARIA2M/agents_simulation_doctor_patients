#!/usr/bin/env python3
# normalize_ck.py — sintetic_patients/patientsCK/ -> patients/
#
#   python normalize_ck.py                 # comprueba, no escribe
#   python normalize_ck.py --write         # escribe en patients/
#   python normalize_ck.py --out DIR       # escribe en otro sitio
#
# Los ficheros CK guardan el BMQ como suma cruda sobre el máximo — 21/25 — que
# no es JSON válido. El denominador codifica el número de ítems, porque cada
# ítem puntúa 1-5: /25 son 5 ítems, /20 son 4. La media por ítem devuelve la
# escala 1-5 que usan las bandas y la evaluación.
#
#     media = numerador / (denominador / 5)
#
# Cualquier otro denominador se rechaza en vez de adivinarlo.

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
SRC = REPO_ROOT / "sintetic_patients" / "patientsCK"

BMQ_KEYS = ["specific_necessity", "specific_concerns", "general_harm", "general_overuse"]
ITEMS_FROM_MAX = {"specific_necessity": 25, "specific_concerns": 25,
                  "general_harm": 20, "general_overuse": 20}

FRACTION = re.compile(r':\s*(\d+)\s*/\s*(\d+)')


class BadFraction(ValueError):
    pass


def _mean(raw: str, key: str) -> float:
    """'21/25' -> 4.2. The denominator must be the one this subscale uses."""
    numerator, maximum = (int(part) for part in raw.split("/"))
    if maximum != ITEMS_FROM_MAX[key]:
        raise BadFraction(f"{key} = {raw}: máximo {maximum}, se esperaba {ITEMS_FROM_MAX[key]}")
    return round(numerator / (maximum / 5), 2)


def normalize_file(path: Path) -> dict:
    """One CK file as a patient profile. Raises rather than repairing."""
    text = FRACTION.sub(lambda m: ': "%s/%s"' % m.groups(), path.read_text())
    profile = json.loads(text)

    bmq = profile["belief_profile"]["bmq"]
    for key in BMQ_KEYS:
        if isinstance(bmq.get(key), str):
            bmq[key] = _mean(bmq[key], key)

    profile["belief_profile"]["bmq"] = {k: bmq[k] for k in BMQ_KEYS}
    return profile


def normalized_corpus(src: Path = SRC) -> dict[str, dict]:
    """Every CK file, keyed by patient id."""
    return {path.stem.replace("_CK", ""): normalize_file(path)
            for path in sorted(src.glob("*_CK.json"))}


def as_json(profile: dict) -> str:
    return json.dumps(profile, indent=2, ensure_ascii=False) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true", help="escribir en patients/")
    parser.add_argument("--out", metavar="DIR", default=None, help="escribir en otro directorio")
    args = parser.parse_args()

    try:
        corpus = normalized_corpus()
    except (BadFraction, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    destination = Path(args.out) if args.out else (REPO_ROOT / "patients" if args.write else None)
    for patient_id, profile in sorted(corpus.items()):
        if destination is None:
            print(f"{patient_id}  {json.dumps(profile['belief_profile']['bmq'])}")
            continue
        destination.mkdir(parents=True, exist_ok=True)
        (destination / f"{patient_id}.json").write_text(as_json(profile))
        print(f"escrito {destination}/{patient_id}.json")

    if destination is None:
        print(f"\n{len(corpus)} pacientes, sin escribir. --write para volcarlos en patients/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
