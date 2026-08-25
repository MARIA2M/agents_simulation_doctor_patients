# ahead_agent/metadata.py
# ─────────────────────────────────────────────
# What a run was made of: models, sampling, prompts, code, machine (0.4).
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

REPO_ROOT = Path(__file__).resolve().parents[1]   # the repo

# `git status` has to stat the whole tree: 24.7 s on GPFS with 20 files.
_COMMAND_TIMEOUT = 60


# ── What a run records ───────────────────────


@dataclass
class RunMetadata:
    run_id: str
    started_at: str
    profile: str
    models: Dict[str, Any] = field(default_factory=dict)
    sampling: Dict[str, Any] = field(default_factory=dict)
    server: Dict[str, Any] = field(default_factory=dict)
    prompts: Dict[str, Any] = field(default_factory=dict)
    code: Dict[str, Any] = field(default_factory=dict)
    compute: Dict[str, Any] = field(default_factory=dict)
    corpus: Dict[str, Any] = field(default_factory=dict)


# ── Building it (0.4) ────────────────────────


def new_run_id() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def hash_text(text: str) -> str:
    """Fingerprint of a composed prompt, so results can be traced to it."""
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def build_metadata(
    config: Dict[str, Any],
    run_id: Optional[str] = None,
    prompt_hashes: Optional[Dict[str, Any]] = None,
    patient_ids: Optional[List[str]] = None,
) -> RunMetadata:
    """Describe a run about to start, from its loaded profile."""
    changes = _command_output("git", "-C", str(REPO_ROOT), "status", "--porcelain")

    code = {
        "git_commit": _command_output("git", "-C", str(REPO_ROOT), "rev-parse", "--short", "HEAD"),
        # with uncommitted changes, git_commit names other code
        "dirty": None if changes is None else bool(changes),
    }

    # §6.3
    compute = {
        "hostname": socket.gethostname(),
        "slurm_nodelist": os.getenv("SLURM_NODELIST"),
        "slurm_job": os.getenv("SLURM_JOB_ID"),
        "gpus": _gpu_count(),
    }

    corpus = {
        "patients": len(patient_ids) if patient_ids is not None else None,
        "patient_ids": list(patient_ids) if patient_ids is not None else None,
        "ground_truth_source": "patients/*.json",
    }

    return RunMetadata(
        run_id=run_id or new_run_id(),
        started_at=datetime.now().astimezone().isoformat(timespec="seconds"),
        profile=config.get("profile", "unknown"),
        models=dict(config.get("models", {})),
        sampling=dict(config.get("sampling", {})),
        server=dict(config.get("server", {})),
        prompts=dict(prompt_hashes or {}),
        code=code,
        compute=compute,
        corpus=corpus,
    )


# ── Writing it out ───────────────────────────


def write_metadata(meta: RunMetadata, runs_dir: Path | str) -> Path:
    """Write runs/<run_id>/metadata.json and return its path."""
    outdir = Path(runs_dir) / meta.run_id
    outdir.mkdir(parents=True, exist_ok=True)
    path = outdir / "metadata.json"
    path.write_text(json.dumps(dataclasses.asdict(meta), indent=2) + "\n")
    return path


# ── Probing the machine (§6.3) ───────────────


def _command_output(*command: str) -> Optional[str]:
    """Output of a command, or None if it fails or takes too long."""
    try:
        result = subprocess.run(
            command, capture_output=True, text=True, timeout=_COMMAND_TIMEOUT
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout.strip() if result.returncode == 0 else None


def _gpu_count() -> Optional[int]:
    """How many GPUs this run really had."""
    allocated = os.getenv("SLURM_GPUS_ON_NODE")
    if allocated and allocated.isdigit():
        return int(allocated)

    listing = _command_output("nvidia-smi", "-L")
    return listing.count("GPU ") if listing else None
