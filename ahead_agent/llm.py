# ahead_agent/llm.py
# ─────────────────────────────────────────────
# One call to the local Ollama server, with the settings the profile declares.
# Transport failures and empty replies are retried; nothing else is (3.1).
# ─────────────────────────────────────────────

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

import httpx

MAX_ATTEMPTS = 3   # tries per call

# role → which model answers
MODEL_FOR_ROLE = {"doctor": "doctor", "patient": "patient", "report": "doctor"}


class TransportError(RuntimeError):
    """The server never gave a usable answer. Says nothing about the model."""


# ── One call ─────────────────────────────────


def chat(
    config: Dict[str, Any],
    role: str,
    messages: List[Dict[str, Any]],
    tools: Optional[List[Dict[str, Any]]] = None,
    events: Optional[List[Dict[str, Any]]] = None,
    usage: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """One /api/chat call. Returns the reply, which may carry tool_calls."""
    url = config["server"]["ollama_url"].rstrip("/") + "/api/chat"
    body = _request_body(config, role, messages, tools)
    timeout = config["server"]["request_timeout"]

    for attempt in range(1, MAX_ATTEMPTS + 1):
        response, failure = _try_once(url, body, timeout)

        if failure is None:
            if usage is not None:                                        # §6.1
                usage.append({"role": role, "eval_tokens": response.get("eval_count"),
                              "prompt_tokens": response.get("prompt_eval_count")})
            return response["message"]

        if events is not None:
            events.append({"event": "llm_retry", "role": role,
                           "attempt": attempt, "failure": failure})
        if attempt < MAX_ATTEMPTS:
            time.sleep(2 * attempt)

    raise TransportError(f"{role}: {MAX_ATTEMPTS} attempts, last failure was {failure}")


# ── What we send (§12) ───────────────────────


def sampling_options(config: Dict[str, Any], role: str) -> Dict[str, Any]:
    """Sent on every call, so the server never gets to choose."""
    sampling = config["sampling"]
    options = {
        "temperature": sampling[role + "_temperature"],
        "num_ctx": sampling["context_length"],
    }
    if sampling.get("seed") is not None:
        options["seed"] = sampling["seed"]
    return options


def _request_body(
    config: Dict[str, Any],
    role: str,
    messages: List[Dict[str, Any]],
    tools: Optional[List[Dict[str, Any]]],
) -> Dict[str, Any]:
    body = {
        "model": config["models"][MODEL_FOR_ROLE[role]],
        "messages": messages,
        "stream": False,
        "options": sampling_options(config, role),
        "keep_alive": config["server"]["keep_alive"],   # §6.1
    }
    if tools:
        body["tools"] = tools
    return body


# ── One try (3.1) ────────────────────────────


def _try_once(url: str, body: Dict[str, Any], timeout: float):
    """One request. Returns (response, None), or (None, why it failed)."""
    try:
        response = _post(url, body, timeout)
        reply = response["message"]
    except (httpx.HTTPError, KeyError, ValueError) as error:
        return None, f"{type(error).__name__}: {error}"

    if reply.get("tool_calls") or (reply.get("content") or "").strip():
        return response, None
    return None, "empty reply"


# the seam test_llm.py monkeypatches
def _post(url: str, body: Dict[str, Any], timeout: float) -> Dict[str, Any]:
    response = httpx.post(url, json=body, timeout=timeout)
    response.raise_for_status()
    return response.json()
