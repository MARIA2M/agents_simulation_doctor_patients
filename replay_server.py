#!/usr/bin/env python3
# replay_server.py
# ─────────────────────────────────────────────
# The consultation viewer: serves a batch that has already been run, so the
# browser can play it back turn by turn and then show what it was worth.
#
#   ./venv-local/bin/python replay_server.py
#   ./venv-local/bin/python replay_server.py --runs runs --port 8000
#
# **It generates nothing.** The original (`ahead_agent_ckakalou/api_server.py`)
# has `/doctor/ask`, `/patient/respond` and `/score` because there the browser
# drives the interview: it walks the questions by index and calls the scorer one
# at a time. Here the transcript already exists and is the whole truth, so those
# three endpoints have nothing to do and are not here. No model, no GPU, no
# graph — post-process, like cover.py and evaluate.py.
#
# There is no `/evaluate` either. `evaluate.py` already writes `evaluation.json`,
# and recomputing the MAE in the browser would be a second implementation of the
# same metric, free to drift from the first. What *is* computed here is the
# comparison for **one consultation**, because the `by_report` of
# `evaluation.json` holds one entry per report and all of them carry the same
# `patient_id`: in a batch of five repeats there is no way to tell which is
# which. It goes through `evaluation.evaluate_patient` — the same function
# evaluate.py calls, not a copy of it.
# ─────────────────────────────────────────────

from __future__ import annotations

import argparse
import dataclasses
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from ahead_agent import corpus, evaluation
from ahead_agent import report as report_module
from ahead_agent.config import load_config

HERE = Path(__file__).resolve().parent
FRONTEND = HERE / "replay_frontend"


# ── Reading from disk ────────────────────────


def _read_json(path: Path) -> Optional[Any]:
    """Whatever is there, or None. A missing post-process file is an ordinary
    state — cover.py may simply not have run — and not a server error."""
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError:
        return None


def _consultation_dirs(batch_dir: Path) -> List[Path]:
    """**The disk decides what exists**, as in coverage._index: a batch resumed
    after a walltime kill rewrites batch.json with that launch's consultations
    alone, so trusting the index loses whole sessions."""
    return sorted(p.parent for p in batch_dir.glob("*/transcript.json"))


def _split_run_name(name: str) -> tuple:
    """`<patient_id>-r<repeat>`, written by the same code that writes the
    transcript, so it cannot disagree with it."""
    patient_id, _, repeat = name.rpartition("-r")
    return (patient_id or name, int(repeat) if repeat.isdigit() else 1)


# ── The index of batches ─────────────────────


def list_runs(runs_dir: Path, patient: Optional[str] = None) -> List[Dict[str, Any]]:
    """One entry per batch with its consultations, for one patient at a time.

    `patient` is not a convenience filter. The unit this viewer shows is **one
    person's consultations**, the way the original ran one interview at a time:
    a wall of ten patients side by side is a corpus summary, and there is already
    a tool for that (`cover.py`). Whole batches drop out when they hold nobody
    asked for, so the caller never has to filter the result again.
    """
    batches = []
    for batch_dir in sorted(p for p in runs_dir.iterdir() if p.is_dir()):
        consultations = [
            d for d in _consultation_dirs(batch_dir)
            if patient is None or _split_run_name(d.name)[0] == patient
        ]
        if not consultations:
            continue   # runs/historic/, and batches without this patient

        index = {c["run"]: c for c in (_read_json(batch_dir / "batch.json") or {}).get(
            "consultations", []) if "run" in c}
        metadata = _read_json(batch_dir / "metadata.json") or {}

        batches.append({
            "batch": batch_dir.name,
            "profile": metadata.get("profile"),
            "features": metadata.get("features") or {},
            "models": metadata.get("models") or {},
            # which post-process has been over this batch already
            "has": {
                name: (batch_dir / f"{name}.json").is_file()
                for name in ("coverage", "fidelity", "evaluation")
            },
            "consultations": [
                {
                    "run": d.name,
                    "patient_id": _split_run_name(d.name)[0],
                    "repeat": _split_run_name(d.name)[1],
                    "stop_reason": (index.get(d.name) or {}).get("stop_reason"),
                    "events": (index.get(d.name) or {}).get("events"),
                    "turns": (index.get(d.name) or {}).get("turns"),
                }
                for d in consultations
            ],
        })
    return batches


# ── One whole consultation ───────────────────


def _entry_for(payload: Optional[dict], key: str, run: str) -> Optional[dict]:
    """This run's entry inside a batch-level file."""
    for item in (payload or {}).get(key) or []:
        if item.get("run") == run:
            return item
    return None


def read_consultation(runs_dir: Path, batch: str, run: str, truth: Dict[str, Any]) -> Dict[str, Any]:
    batch_dir = runs_dir / batch
    run_dir = batch_dir / run
    if not (run_dir / "transcript.json").is_file():
        raise HTTPException(404, f"{batch}/{run}: no transcript.json")

    transcript = _read_json(run_dir / "transcript.json") or {}
    stored = _read_json(run_dir / "report.json") or {}
    patient_id = transcript.get("patient_id") or _split_run_name(run)[0]

    # Re-parsed rather than taken on trust, which is what evaluate.py and
    # coverage.py do: the NA policy of 4.4 is applied here too.
    parsed = (
        report_module.parse(json.dumps(stored["report"]), patient_id)
        if stored.get("report") else None
    )

    profile = truth.get(patient_id) or {}
    beliefs = profile.get("belief_profile") or {}

    # This consultation's comparison, through the function evaluate.py uses.
    per_run = None
    if parsed and beliefs:
        metrics = evaluation.evaluate_patient(parsed, beliefs)
        # coverage_rate is a property, not a field, so asdict does not carry it
        per_run = {**dataclasses.asdict(metrics), "coverage_rate": metrics.coverage_rate}

    return {
        "batch": batch,
        "run": run,
        "patient_id": patient_id,
        "repeat": _split_run_name(run)[1],
        "arm": _read_json(batch_dir / "metadata.json") or {},
        # The clinical profile is what the patient was playing. Showing it here
        # does not touch invariant 1: what the doctor must never see is the
        # belief_profile *during* the consultation, and this is post mortem.
        "clinical": profile.get("disease_profile") or {},
        "truth": beliefs,
        "transcript": {
            "turns": transcript.get("turns"),
            "stop_reason": transcript.get("stop_reason"),
            "events": transcript.get("events") or [],
            "conversation": transcript.get("conversation") or [],
            "coverage_hint": transcript.get("coverage_hint") or {},
        },
        "report": dataclasses.asdict(parsed) if parsed else None,
        "report_parsed": stored.get("parsed"),
        "report_attempts": stored.get("attempts"),
        "evaluation": per_run,
        # Optional post-process: absent until cover.py / fidel.py have run.
        "coverage": _entry_for(_read_json(batch_dir / "coverage.json"),
                               "by_consultation", run),
        "fidelity": _entry_for(_read_json(batch_dir / "fidelity.json"), "by_run", run),
    }


# ── The application ──────────────────────────


def list_patients(runs_dir: Path, truth: Dict[str, Any],
                  only: Optional[str] = None) -> List[Dict[str, Any]]:
    """Who there is anything to look at for, and how much of it.

    Read from the directory names rather than from the corpus: a patient with a
    profile but no consultation is nothing to offer, and one whose runs are on
    disk but whose profile is gone still has a transcript worth reading.
    """
    counts: Dict[str, Dict[str, Any]] = {}
    for batch_dir in sorted(p for p in runs_dir.iterdir() if p.is_dir()):
        for run_dir in _consultation_dirs(batch_dir):
            patient_id = _split_run_name(run_dir.name)[0]
            if only is not None and patient_id != only:
                continue
            entry = counts.setdefault(patient_id, {"patient_id": patient_id,
                                                   "consultations": 0, "batches": set()})
            entry["consultations"] += 1
            entry["batches"].add(batch_dir.name)

    out = []
    for entry in sorted(counts.values(), key=lambda e: e["patient_id"]):
        clinical = (truth.get(entry["patient_id"]) or {}).get("disease_profile") or {}
        out.append({
            "patient_id": entry["patient_id"],
            "consultations": entry["consultations"],
            "batches": len(entry["batches"]),
            "diagnosis": clinical.get("diagnosis"),
            "treatment_regimen": clinical.get("treatment_regimen"),
            "age": (clinical.get("demographics") or {}).get("age"),
        })
    return out


def build_app(runs_dir: Path, patients_dir: Path, only: Optional[str] = None) -> FastAPI:
    app = FastAPI(title="AHEAD — consultation viewer")
    truth = corpus.load_corpus(patients_dir)

    @app.get("/api/patients")
    def patients():
        return list_patients(runs_dir, truth, only)

    @app.get("/api/runs")
    def runs(patient: Optional[str] = None):
        # `only` wins over the query string: a server started for one patient
        # cannot be talked out of it from the browser.
        return list_runs(runs_dir, only or patient)

    @app.get("/api/runs/{batch}/{run}")
    def consultation(batch: str, run: str):
        # Both come from the URL and are used as directory names: without this a
        # `..` in either one reads outside runs/.
        if any(part in (".", "..") or "/" in part for part in (batch, run)):
            raise HTTPException(400, "not a valid batch or consultation name")
        return read_consultation(runs_dir, batch, run, truth)

    @app.get("/")
    def index():
        return FileResponse(FRONTEND / "index.html")

    app.mount("/static", StaticFiles(directory=FRONTEND), name="static")
    return app


def main() -> None:
    parser = argparse.ArgumentParser(description="Viewer for batches already run")
    parser.add_argument("--runs", default=None, help="the batch directory")
    parser.add_argument("--patient", default=None, metavar="ID",
                        help="serve only this patient, e.g. CLL-003. Without it "
                             "the browser picks one first — it never shows the "
                             "whole corpus at once either way")
    parser.add_argument("--profile", default="local", help="run profile, for paths")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--host", default="127.0.0.1")
    args = parser.parse_args()

    config = load_config(args.profile)
    runs_dir = Path(args.runs) if args.runs else config["paths"]["runs"]
    if not runs_dir.is_dir():
        raise SystemExit(f"{runs_dir}: no such directory")

    import uvicorn

    truth = corpus.load_corpus(config["paths"]["patients"])
    people = list_patients(runs_dir, truth, args.patient)
    if not people:
        raise SystemExit(
            f"{runs_dir}: nothing to show"
            + (f" for {args.patient}" if args.patient else "")
        )

    print(f"  runs      : {runs_dir}")
    for person in people:
        print(f"  {person['patient_id']:12} {person['consultations']:>3} consultations "
              f"over {person['batches']} batches")
    print(f"  listening : http://{args.host}:{args.port}")

    uvicorn.run(build_app(runs_dir, config["paths"]["patients"], args.patient),
                host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
