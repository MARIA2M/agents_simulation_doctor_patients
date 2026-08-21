#!/usr/bin/env python3
# main.py
# One consultation: loads the profile, writes the metadata of the run, lets
# doctor and patient talk until the doctor closes, and saves the transcript.
#
#   python main.py --patient patients/HIV-001.json
#   python main.py --patient patients/CLL-003.json --profile hpc

import argparse
import json
from pathlib import Path

from ahead_agent import prompts
from ahead_agent.config import load_config
from ahead_agent.graph import build_graph
from ahead_agent.metadata import build_metadata, write_metadata
from ahead_agent.report import write_report, write_transcript
from ahead_agent.state import State


def load_patient(path: str) -> dict:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Patient profile not found: {path}")
    with open(p) as f:
        return json.load(f)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=" "
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


def print_header(config: dict, patient: dict, meta) -> None:
    disease = patient["disease_profile"]
    demographics = disease["demographics"]

    print("═" * 62)
    print("  AHEAD consultation")
    print(f"  Run            : {meta.run_id}  ({meta.profile})")
    print(f"  Patient        : {patient.get('patient_id', 'unknown')}")
    print(f"  Disease        : {disease['diagnosis']}")
    print(f"  Demographics   : {demographics['age']} y/o {demographics['gender']}")
    print(f"  Doctor model   : {config['models']['doctor']}")
    print(f"  Patient model  : {config['models']['patient']}")
    print("  Temperature    : " + ", ".join(f"{name.removesuffix('_temperature')} {value}" \
                                             for name, value in config["sampling"].items() if name.endswith("_temperature")))
    print("═" * 62)

    if meta.code.get("dirty"):
        print("  ! working tree is dirty — this run cannot be traced to its commit")


# def print_summary(final_state, transcript: Path) -> None:
#     turns = final_state.turn_count
#     events = final_state.events

#     print(f"  turns          : {turns}  (ended by {final_state.stop_reason})")
#     print(f"  transcript     : {transcript}")
#     if events:
#         print(f"  ! {len(events)} events — this run is not clean, see the transcript")


def main() -> None:
    args = parse_args()
    config = load_config(args.profile)
    patient = load_patient(args.patient)

    meta = build_metadata(
        config,
        run_id=args.run_id,
        prompt_hashes=prompts.hashes(config),
        patient_ids=[patient.get("patient_id", "unknown")],
    )
    print_header(config, patient, meta)

    runs_dir = Path(args.runs_dir) if args.runs_dir else config["paths"]["runs"]
    metadata = write_metadata(meta, runs_dir)
    print(f"  metadata       : {metadata}")

    app = build_graph(config)
    final_state = State(**app.invoke(State(config, patient)))

    transcript = write_transcript(final_state, runs_dir / meta.run_id)
    write_report(final_state, runs_dir / meta.run_id)
    #print_summary(final_state, transcript)


if __name__ == "__main__":
    main()
