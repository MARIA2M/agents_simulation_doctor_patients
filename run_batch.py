#!/usr/bin/env python3
# run_batch.py
# ─────────────────────────────────────────────
# N repeats × M patients under one configuration — the unit of measurement of
# this project, because nothing it wants to know is visible at n=1.
#
# The spread of one patient across repeats is the empirical confidence of 2.4;
# the spread of the means across patients is the discrimination of 2.5. They are
# only meaningful together: a scorer that answers the same thing every time has
# perfect confidence and zero discrimination, which is what llama3.2 did with
# its 67% of eights (P4) and what GLM does one register at a time (N5).
#
#   python run_batch.py --profile hpc --repeats 2
#   python run_batch.py --profile local --repeats 1 --patients patients/CLL-003.json
# ─────────────────────────────────────────────

import argparse
import json
from pathlib import Path

from ahead_agent import corpus, llm, prompts
from ahead_agent.config import load_config
from ahead_agent.graph import build_graph
from ahead_agent.metadata import build_metadata, write_metadata
from ahead_agent.report import write_report, write_transcript
from ahead_agent.state import State


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="N repeats × M patients, one configuration")
    parser.add_argument("--repeats", metavar="N", type=int, default=1,
                        help="Consultations per patient. Default: 1")
    parser.add_argument("--patients", metavar="PATH", nargs="*", default=None,
                        help="Profiles to run. Default: every patient in the profile's paths.patients")
    parser.add_argument("--profile", metavar="NAME", default="local",
                        help="Run profile: local (smoke) or hpc (batches). Default: local")
    parser.add_argument("--run-id", metavar="ID", default=None,
                        help="Name of this batch. Default: a timestamp")
    parser.add_argument("--runs-dir", metavar="PATH", default=None,
                        help="Where the batch directory is written. Default: the profile's paths.runs")
    parser.add_argument("--allow-dirty", action="store_true",
                        help="Run with uncommitted changes. The batch is then untraceable")
    return parser.parse_args()


def load_patients(config: dict, given) -> list:
    """The profiles to run, in a fixed order so two batches line up."""
    paths = sorted(Path(p) for p in given) if given else sorted(config["paths"]["patients"].glob("*.json"))
    if not paths:
        raise SystemExit("No patient profiles to run")

    missing = [p for p in paths if not p.exists()]
    if missing:
        raise SystemExit("Not found: " + ", ".join(str(p) for p in missing))

    return corpus.load_patients(paths)


def warm_up(config: dict) -> None:
    """Pull the weights onto the GPU before anything is measured (§6.1).

    A cold load from GPFS is minutes, and paid inside the first turn it would
    land in that consultation's timings and against the request timeout.
    """
    for role in ("doctor", "patient"):
        llm.chat(config, role, [{"role": "user", "content": "hi"}])


def check(config: dict, meta, allow_dirty: bool) -> None:
    """What makes a batch worth keeping, checked before it costs anything."""
    if meta.code.get("dirty") and not allow_dirty:
        raise SystemExit(
            "The working tree is dirty, so git_commit names other code and this "
            "batch could not be reproduced. Commit first, or --allow-dirty."
        )

    sampling = config["sampling"]
    if not sampling["doctor_temperature"] and not sampling["patient_temperature"]:
        print("  ! both temperatures are 0 — the runs will be identical and 2.4 has nothing to measure")


def consult(config, patient: dict, outdir: Path) -> dict:
    """One consultation, written where the batch expects it."""
    app = build_graph(config)
    final = State(**app.invoke(State(config, patient)))

    outdir.mkdir(parents=True, exist_ok=True)
    write_transcript(final, outdir)
    write_report(final, outdir)

    report = final.report
    return {
        "turns": final.turn_count,
        "stop_reason": final.stop_reason,
        "events": len(final.events),
        "report_parsed": report is not None,
        "report_attempts": final.report_attempts,
        # Which dimensions came back NA, not how many: a hole in the coverage
        # map of 3.2 is a place, not a count (4.4).
        "na": sorted(
            name
            for scored in ((report.bipq, report.bmq) if report else ())
            for name, dimension in scored.items()
            if dimension.score is None
        ),
    }


def main() -> None:
    args = parse_args()
    config = load_config(args.profile)
    patients = load_patients(config, args.patients)

    meta = build_metadata(
        config,
        run_id=args.run_id,
        prompt_hashes=prompts.hashes(config),
        patient_ids=[p.get("patient_id", "unknown") for p in patients],
    )
    check(config, meta, args.allow_dirty)

    runs_dir = Path(args.runs_dir) if args.runs_dir else config["paths"]["runs"]
    batch_dir = runs_dir / meta.run_id
    total = len(patients) * args.repeats

    print("═" * 62)
    print("  AHEAD batch")
    print(f"  Batch          : {meta.run_id}  ({meta.profile})")
    print(f"  Consultations  : {len(patients)} patients × {args.repeats} = {total}")
    print(f"  Doctor model   : {config['models']['doctor']}")
    print(f"  Patient model  : {config['models']['patient']}")
    print("═" * 62)

    print(f"  metadata       : {write_metadata(meta, runs_dir)}")
    warm_up(config)

    index = {"batch_id": meta.run_id, "repeats": args.repeats, "consultations": []}
    done = 0

    # Repeat-major: one sweep of the whole corpus, then the next. A batch cut
    # short by the queue then holds every patient once instead of two patients
    # ten times, and 2.5 needs the patients more than 2.4 needs the repeats.
    for repeat in range(1, args.repeats + 1):
        for patient in patients:
            patient_id = patient.get("patient_id", "unknown")
            name = f"{patient_id}-r{repeat}"
            outdir = batch_dir / name
            done += 1

            # Already there: a re-launch after a walltime kill picks up where
            # the queue cut it off instead of paying for it twice.
            if (outdir / "transcript.json").exists():
                print(f"\n[{done}/{total}] {name} — already run, skipped")
                continue

            print(f"\n[{done}/{total}] {name}")
            record = {"run": name, "patient_id": patient_id, "repeat": repeat}
            try:
                record.update(status="ok", **consult(config, patient, outdir))
            except Exception as error:  # noqa: BLE001 — one lost consultation is not a lost batch
                record.update(status="failed", error=f"{type(error).__name__}: {error}")
                print(f"  ! failed: {record['error']}")

            index["consultations"].append(record)
            # Written every time: a batch killed by the queue still leaves an
            # index that says what it got through.
            (batch_dir / "batch.json").write_text(json.dumps(index, indent=2) + "\n")

    failed = [c for c in index["consultations"] if c["status"] == "failed"]
    unparsed = [c for c in index["consultations"] if c.get("report_parsed") is False]

    print("\n" + "═" * 62)
    print(f"  batch          : {batch_dir}")
    print(f"  failed         : {len(failed)}")
    print(f"  unparsed report: {len(unparsed)}")
    print("  A batch with either is not a corpus to analyse yet (3.4).")


if __name__ == "__main__":
    main()
