# ahead_agent/report.py
# What a run leaves behind. The report schema itself arrives in stage 3.

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict


def write_transcript(final_state, outdir: Path) -> Path:
    """The consultation as it happened, next to the metadata of the run.

    The patient's belief_profile is deliberately left out: ground truth is read
    from patients/*.json and from nowhere else (4.1), and a copy sitting beside
    the transcript is how a run ends up scored against itself.
    """
    transcript = {
        "patient_id": final_state.patient.get("patient_id"),
        "turns": final_state.turn_count,
        "stop_reason": final_state.stop_reason,
        "conversation": final_state.conversation,
        "events": final_state.events,
        "usage": final_state.usage,
    }

    path = outdir / "transcript.json"
    path.write_text(json.dumps(transcript, indent=2) + "\n")
    return path
