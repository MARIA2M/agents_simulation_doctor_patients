# ahead_agent/run_meta.py
# ─────────────────────────────────────────────
# Per-run provenance (0.4).
#
# Everything needed to interpret a run's outputs months later: which models,
# which sampling settings, which prompts, which code, which machine.
# Written once when the run starts, next to its outputs.
#
# Without this the "one variable per run" method does not work: when the MAE
# moves between two runs there is no way to tell the change you made from
# anything else that drifted.
#
# Precedent: the manifest.json of run_config.rb in the Ruby arm.
# ─────────────────────────────────────────────

from __future__ import annotations

import dataclasses
import hashlib
import json
import os
import socket
import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

REPO_ROOT = Path(__file__).resolve().parents[1]

# Git and nvidia-smi are convenience lookups, never the point of the run, so
# they are capped and degrade to None rather than stalling a batch.
#
# The cap is generous because `git status` has to stat the whole tree, and on
# GPFS that is slow out of proportion to the repository: measured at 24.7 s
# with 20 files, against 2.6 s for `git rev-parse`, which only reads .git.
# Too tight a cap turns `dirty` into None on every run, which is exactly the
# blind spot it exists to remove.
_PROBE_TIMEOUT = 60


@dataclass
class RunMeta:
    """Provenance of a single run. Serialised to runs/<run_id>/run_meta.json."""

    run_id: str
    started_at: str
    profile: str
    models: Dict[str, Any] = field(default_factory=dict)
    sampling: Dict[str, Any] = field(default_factory=dict)
    prompts: Dict[str, Any] = field(default_factory=dict)
    code: Dict[str, Any] = field(default_factory=dict)
    compute: Dict[str, Any] = field(default_factory=dict)
    corpus: Dict[str, Any] = field(default_factory=dict)


# ── Public API ───────────────────────────────


def new_run_id() -> str:
    """Timestamp run id, same shape as the Ruby arm's RUN_ID."""
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def build_run_meta(
    config: Dict[str, Any],
    run_id: Optional[str] = None,
    prompt_hashes: Optional[Dict[str, Any]] = None,
    patient_ids: Optional[List[str]] = None,
) -> RunMeta:
    """Collect provenance for a run about to start.

    `config` is the loaded run profile (§6); its `models` and `sampling`
    blocks are copied verbatim, so what is recorded is what will be sent —
    not what the defaults are assumed to be (§12).
    """
    return RunMeta(
        run_id=run_id or new_run_id(),
        started_at=datetime.now().astimezone().isoformat(timespec="seconds"),
        profile=config.get("profile", "unknown"),
        models=dict(config.get("models", {})),
        sampling=dict(config.get("sampling", {})),
        prompts=dict(prompt_hashes or {}),
        code=_code_provenance(),
        compute=_compute_provenance(),
        corpus=_corpus_provenance(patient_ids),
    )


def write_run_meta(meta: RunMeta, runs_dir: Path | str) -> Path:
    """Write runs/<run_id>/run_meta.json, creating the run directory."""
    outdir = Path(runs_dir) / meta.run_id
    outdir.mkdir(parents=True, exist_ok=True)
    path = outdir / "run_meta.json"
    path.write_text(json.dumps(dataclasses.asdict(meta), indent=2) + "\n")
    return path


def hash_text(text: str) -> str:
    """Content hash of an already-composed prompt (§5.1)."""
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


# ── Provenance collectors ────────────────────


def _code_provenance() -> Dict[str, Any]:
    """Commit that produced the run, and whether it can be trusted.

    `dirty` matters as much as the commit: with uncommitted changes in the
    tree, `git_commit` names code that is not the code that ran.
    """
    return {
        "git_commit": _git("rev-parse", "--short", "HEAD"),
        "dirty": _git_dirty(),
    }


def _compute_provenance() -> Dict[str, Any]:
    """Where the run actually executed.

    `hostname` and `slurm_nodelist` are both recorded on purpose: salloc
    without srun runs on the login node while the reserved node sits idle,
    and on the ACC partition the login nodes have H100s too, so nothing else
    gives it away (§6.3). If these two disagree, the run did not happen where
    it was meant to.
    """
    return {
        "hostname": socket.gethostname(),
        "slurm_job": os.getenv("SLURM_JOB_ID"),
        "slurm_nodelist": os.getenv("SLURM_NODELIST"),
        "gpus": _gpu_count(),
    }


def _corpus_provenance(patient_ids: Optional[List[str]]) -> Dict[str, Any]:
    return {
        "patients": len(patient_ids) if patient_ids is not None else None,
        "patient_ids": list(patient_ids) if patient_ids is not None else None,
        "ground_truth_source": "patients/*.json",
    }


# ── Helpers ──────────────────────────────────


def _git(*args: str) -> Optional[str]:
    """Run a git command in the repo, or None if it cannot be answered."""
    try:
        result = subprocess.run(
            ["git", "-C", str(REPO_ROOT), *args],
            capture_output=True,
            text=True,
            timeout=_PROBE_TIMEOUT,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout.strip() if result.returncode == 0 else None


def _git_dirty() -> Optional[bool]:
    status = _git("status", "--porcelain")
    return None if status is None else bool(status)


def _gpu_count() -> Optional[int]:
    """GPUs the job was given.

    SLURM is asked first and nvidia-smi only as a fallback: on a login node
    nvidia-smi reports the machine's GPUs, not the ones allocated (§6.3).
    """
    allocated = os.getenv("SLURM_GPUS_ON_NODE")
    if allocated and allocated.isdigit():
        return int(allocated)

    listing = _nvidia_smi_list()
    return listing.count("GPU ") if listing else None


def _nvidia_smi_list() -> Optional[str]:
    try:
        result = subprocess.run(
            ["nvidia-smi", "-L"],
            capture_output=True,
            text=True,
            timeout=_PROBE_TIMEOUT,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout if result.returncode == 0 else None
