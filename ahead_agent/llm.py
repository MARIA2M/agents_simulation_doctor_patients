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

EMPTY_REPLY = "empty reply"

# Floor the temperature is raised to after an empty reply, per retry. A
# transport failure is the server not answering and the same request is the one
# to repeat; an empty reply is the model answering with nothing, and at
# temperature 0 the next draw is the same nothing (N10). Only raises: a role
# already sampling above the floor is left alone.
RESAMPLE_FLOOR = (0.3, 0.6)


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
    timeout = config["server"]["request_timeout"]
    empties = 0   # empty replies so far, which is what moves the sampling

    for attempt in range(1, MAX_ATTEMPTS + 1):
        # Rebuilt per attempt: the body is not constant once an empty reply has
        # to come back different.
        body = _request_body(config, role, messages, tools, empties)
        response, failure = _try_once(url, body, timeout)

        if failure is None:
            if usage is not None:                                        # §6.1
                usage.append({"role": role, "eval_tokens": response.get("eval_count"),
                              "prompt_tokens": response.get("prompt_eval_count")})
            return response["message"]

        if failure == EMPTY_REPLY:
            empties += 1

        if events is not None:
            event = {"event": "llm_retry", "role": role,
                     "attempt": attempt, "failure": failure}
            resampled = _resampled_temperature(config, role, empties)
            if resampled is not None:
                event["retry_temperature"] = resampled
            events.append(event)
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


def _resampled_temperature(config: Dict[str, Any], role: str, empties: int) -> Optional[float]:
    """The temperature the next attempt needs, or None when it needs no change."""
    if not empties:
        return None
    floor = RESAMPLE_FLOOR[min(empties, len(RESAMPLE_FLOOR)) - 1]
    base = config["sampling"][role + "_temperature"]
    return floor if floor > base else None


def _request_body(
    config: Dict[str, Any],
    role: str,
    messages: List[Dict[str, Any]],
    tools: Optional[List[Dict[str, Any]]],
    empties: int = 0,
) -> Dict[str, Any]:
    options = sampling_options(config, role)
    resampled = _resampled_temperature(config, role, empties)
    if resampled is not None:
        options["temperature"] = resampled
    # A pinned seed makes the draw identical whatever the temperature, so it
    # moves too. Only on a retry: attempt 1 is the seed the profile declared.
    if empties and options.get("seed") is not None:
        options["seed"] = options["seed"] + empties
    body = {
        "model": config["models"][MODEL_FOR_ROLE[role]],
        "messages": messages,
        "stream": False,
        "options": options,
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
    return None, EMPTY_REPLY


# the seam test_llm.py monkeypatches
def _post(url: str, body: Dict[str, Any], timeout: float) -> Dict[str, Any]:
    response = httpx.post(url, json=body, timeout=timeout)
    response.raise_for_status()
    return response.json()
