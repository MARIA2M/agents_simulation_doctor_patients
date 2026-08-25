# tests/test_metadata.py
# The run metadata is collected and saved complete (0.4).
# build_metadata shells out to git (~25 s on GPFS), so the module shares one.

import dataclasses
import json
import re

import pytest

from ahead_agent.llm import sampling_options
from ahead_agent.metadata import build_metadata, hash_text, new_run_id, write_metadata

PROFILE = {
    "profile": "local",
    "models": {"doctor": "llama3.2", "patient": "dolphin-llama3", "embed": "nomic-embed-text"},
    # Flat keys per role, as config/*.yaml has them and `llm.sampling_options`
    # reads them. This was once nested as `temperature: {doctor: …}`, which is
    # no real profile's shape: the test passed either way because
    # `build_metadata` copies the block verbatim, so it could not fail for the
    # reason it was written.
    "sampling": {
        "doctor_temperature": 0.7,
        "patient_temperature": 0.7,
        "report_temperature": 0.0,
        "seed": None,
        "context_length": 32768,
        "num_parallel": 1,
    },
    "server": {"ollama_url": "http://127.0.0.1:11434", "request_timeout": 300},
    "features": {"coverage_hint": "show", "working_notes": True},
}


@pytest.fixture(scope="module")
def meta():
    return build_metadata(
        PROFILE,
        prompt_hashes={"doctor": hash_text("# DOCTOR")},
        patient_ids=["CLL-001", "HIV-001"],
    )


# ── What gets recorded ───────────────────────


def test_every_provenance_block_is_present(meta):
    for block in ("models", "sampling", "server", "features", "prompts", "code", "compute", "corpus"):
        assert getattr(meta, block), f"{block} is empty"


def test_endpoint_is_recorded(meta):
    """Invariant 8 — everything runs locally — is only auditable if this is kept."""
    assert meta.server["ollama_url"] == PROFILE["server"]["ollama_url"]


def test_models_and_sampling_are_copied_verbatim(meta):
    """What is recorded is what will be sent, not what the defaults are (§12)."""
    assert meta.models == PROFILE["models"]
    assert meta.sampling == PROFILE["sampling"]


@pytest.mark.parametrize("role", ["doctor", "patient", "report"])
def test_the_temperature_recorded_is_the_one_that_will_be_sent(meta, role):
    """A server applying its own default is invisible unless this is explicit.

    Compared against `llm.sampling_options`, which is what puts it in the
    request: metadata recording one number is worthless if another travels, and
    these are two separate reads of the same block (§12).
    """
    assert meta.sampling[f"{role}_temperature"] == sampling_options(PROFILE, role)["temperature"]


def test_the_arm_is_recorded(meta):
    """Which arm a run belongs to (§4.1). With base.yaml holding the shared
    blocks, `features` is no longer in the profile file, so a run that is not
    the baseline is indistinguishable from one that is unless it lands here."""
    assert meta.features == PROFILE["features"]


def test_code_provenance_answers_both_questions(meta):
    """A commit alone is not provenance: with a dirty tree it names other code."""
    assert set(meta.code) == {"git_commit", "dirty"}
    assert meta.code["git_commit"], "not a git repository?"
    assert meta.code["dirty"] is not None, "dirty is unknown — probe timed out"


def test_compute_records_both_hostname_and_nodelist(meta):
    """salloc without srun runs on the login node; only the pair reveals it (§6.3)."""
    assert "hostname" in meta.compute and "slurm_nodelist" in meta.compute
    assert meta.compute["hostname"]


def test_corpus_records_the_patients_and_their_source(meta):
    assert meta.corpus["patients"] == 2
    assert meta.corpus["patient_ids"] == ["CLL-001", "HIV-001"]
    assert meta.corpus["ground_truth_source"] == "patients/*.json"


def test_started_at_carries_a_timezone(meta):
    """A bare timestamp cannot be compared against a run from another machine."""
    assert re.search(r"[+-]\d{2}:\d{2}$", meta.started_at)


def test_run_id_is_a_timestamp():
    assert re.fullmatch(r"\d{8}-\d{6}", new_run_id())


# ── Serialisation ────────────────────────────


def test_serialises_completely(meta):
    """Nothing may be lost on the way to disk — this is the file you read later."""
    restored = json.loads(json.dumps(dataclasses.asdict(meta)))
    assert restored == dataclasses.asdict(meta)
    assert set(restored) == {
        "run_id", "started_at", "profile", "models", "sampling", "server",
        "features", "prompts", "code", "compute", "corpus",
    }


def test_write_creates_the_run_directory(tmp_path, meta):
    path = write_metadata(meta, tmp_path)

    assert path == tmp_path / meta.run_id / "metadata.json"
    assert json.loads(path.read_text())["run_id"] == meta.run_id


# ── Prompt hashing ───────────────────────────


def test_hash_is_deterministic_and_content_sensitive():
    """This is what attributes a change in results to a change in a prompt (§5.1)."""
    assert hash_text("ask about beliefs") == hash_text("ask about beliefs")
    assert hash_text("ask about beliefs") != hash_text("ask about beliefs.")
    assert hash_text("").startswith("sha256:")
