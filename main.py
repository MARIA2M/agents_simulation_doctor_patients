#!/usr/bin/env python3
# main.py
# Opens a run: loads the profile, writes its metadata, and stops.
# The consultation loop arrives in stage 2.
#
#   python main.py --patient patients/HIV-001.json
#   python main.py --patient patients/CLL-003.json --profile hpc

import argparse
import json
from pathlib import Path

from ahead_agent.config import CONFIG, load_config, path_for
from ahead_agent.metadata import build_metadata, write_metadata


def load_patient(path: str) -> dict:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Patient profile not found: {path}")
    with open(p) as f:
        return json.load(f)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="AHEAD — a doctor LLM infers illness and treatment beliefs "
                    "from a free consultation, and is scored against the "
                    "belief_profile of the patient it spoke to."
    )
    parser.add_argument(
        "--patient",
        metavar="PATH",
        required=True,
        help="Path to a patient JSON profile, e.g. patients/HIV-001.json",
    )
    parser.add_argument(
        "--profile",
        metavar="NAME",
        default="local",
        help="Run profile: local (smoke) or hpc (batches). Default: local",
    )
    parser.add_argument(
        "--run-id",
        metavar="ID",
        default=None,
        help="Name of this run. Default: a timestamp",
    )
    parser.add_argument(
        "--runs-dir",
        metavar="PATH",
        default=None,
        help="Where run directories are written. Default: the profile's paths.runs",
    )
    return parser.parse_args()


def print_header(patient: dict, meta) -> None:
    disease = patient["disease_profile"]
    demographics = disease["demographics"]
    temperatures = CONFIG["sampling"]["temperature"]

    print("═" * 62)
    print("  AHEAD consultation")
    print(f"  Run            : {meta.run_id}  ({meta.profile})")
    print(f"  Patient        : {patient.get('patient_id', 'unknown')}")
    print(f"  Disease        : {disease['diagnosis']}")
    print(f"  Demographics   : {demographics['age']} y/o {demographics['gender']}")
    print(f"  Doctor model   : {CONFIG['models']['doctor']}")
    print(f"  Patient model  : {CONFIG['models']['patient']}")
    print("  Temperature    : " + ", ".join(f"{r} {t}" for r, t in temperatures.items()))
    print("═" * 62)

    if meta.code.get("dirty"):
        print("  ! working tree is dirty — this run cannot be traced to its commit")


def main() -> None:
    args = parse_args()
    load_config(args.profile)
    patient = load_patient(args.patient)

    # prompt_hashes stays empty until prompts.py composes them (stage 2).
    meta = build_metadata(
        CONFIG,
        run_id=args.run_id,
        patient_ids=[patient.get("patient_id", "unknown")],
    )
    print_header(patient, meta)

    runs_dir = Path(args.runs_dir) if args.runs_dir else path_for("runs")
    print(f"  metadata       : {write_metadata(meta, runs_dir)}")
    print("  consultation   : not built yet — stage 2")


if __name__ == "__main__":
    main()
