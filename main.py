#!/usr/bin/env python3
# main.py
# ─────────────────────────────────────────────
# CLI entry point.
#
# Usage:
#   python main.py --patient patients/HIV-001.json
#   python main.py --patient patients/CLL-003.json --profile hpc
#
# Stage 1 only opens the run: it loads the profile, records provenance and
# stops. Nothing here talks to an LLM yet — the consultation loop is stage 2.
# ─────────────────────────────────────────────

import argparse
import json
from pathlib import Path

from ahead_agent.config import CONFIG, load_config, path_for
from ahead_agent.run_meta import build_run_meta, write_run_meta


def load_profile(path: str) -> dict:
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


def print_header(profile: dict, meta) -> None:
    dp = profile["disease_profile"]
    demo = dp["demographics"]

    print("═" * 62)
    print("  AHEAD consultation")
    print(f"  Run            : {meta.run_id}  ({meta.profile})")
    print(f"  Patient        : {profile.get('patient_id', 'unknown')}")
    print(f"  Disease        : {dp['diagnosis']}")
    print(f"  Demographics   : {demo['age']} y/o {demo['gender']}")
    print(f"  Doctor model   : {CONFIG['models']['doctor']}")
    print(f"  Patient model  : {CONFIG['models']['patient']}")
    print(f"  Temperature    : {CONFIG['sampling']['temperature']}")
    print("═" * 62)

    # An uncommitted tree means git_commit names code that is not the code
    # that ran, so the run is not reproducible from its own metadata (§3.2).
    if meta.code.get("dirty"):
        print("  ! working tree is dirty — this run is not reproducible from its commit")


def main() -> None:
    args = parse_args()
    load_config(args.profile)
    profile = load_profile(args.patient)

    # prompt_hashes stays empty until prompts.py composes them (stage 2).
    meta = build_run_meta(
        CONFIG,
        run_id=args.run_id,
        patient_ids=[profile.get("patient_id", "unknown")],
    )
    print_header(profile, meta)

    runs_dir = Path(args.runs_dir) if args.runs_dir else path_for("runs")
    print(f"  run_meta       : {write_run_meta(meta, runs_dir)}")
    print("  consultation   : not built yet — stage 2")


if __name__ == "__main__":
    main()
