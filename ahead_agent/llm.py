# ahead_agent/llm.py
# One call to the local Ollama server, with the settings the profile declares.
# Transport failures and empty replies are retried; nothing else is (3.1).

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

import httpx

MAX_ATTEMPTS = 3

# The report is written by the doctor's model, at its own temperature.
MODEL_FOR_ROLE = {"doctor": "doctor", "patient": "patient", "report": "doctor"}


class TransportError(RuntimeError):
    """The server never gave a usable answer. Says nothing about the model."""


def chat(
    config: Dict[str, Any],
    role: str,
    messages: List[Dict[str, Any]],
    tools: Optional[List[Dict[str, Any]]] = None,
    events: Optional[List[Dict[str, Any]]] = None,
    usage: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """One /api/chat call. Returns the reply, which may carry tool_calls."""
    payload = {
        "model": config["models"][MODEL_FOR_ROLE[role]],
        "messages": messages,
        "stream": False,
        "options": sampling_options(config, role),
        # How long the model stays resident. Left to the server it is five
        # minutes, and reloading costs ~10 s locally, minutes off GPFS (§6.1).
        "keep_alive": config["server"]["keep_alive"],
    }
    if tools:
        payload["tools"] = tools

    url = config["server"]["ollama_url"].rstrip("/") + "/api/chat"
    timeout = config["server"]["request_timeout"]

    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            response = _post(url, payload, timeout)
            reply = response["message"]
        except (httpx.HTTPError, KeyError, ValueError) as error:
            failure = f"{type(error).__name__}: {error}"
        else:
            if reply.get("tool_calls") or (reply.get("content") or "").strip():
                if usage is not None:
                    # What the call actually cost, to size context_length from
                    # measurements instead of from a number copied over.
                    usage.append(
                        {
                            "role": role,
                            "prompt_tokens": response.get("prompt_eval_count"),
                            "eval_tokens": response.get("eval_count"),
                        }
                    )
                return reply
            # An empty turn is a failure to retry now, not a turn to keep: the
            # previous corpus was 19% of them (3.1).
            failure = "empty reply"

        if events is not None:
            events.append(
                {"event": "llm_retry", "role": role, "attempt": attempt, "failure": failure}
            )
        if attempt < MAX_ATTEMPTS:
            time.sleep(2 * attempt)

    raise TransportError(f"{role}: {MAX_ATTEMPTS} attempts, last failure was {failure}")


def sampling_options(config: Dict[str, Any], role: str) -> Dict[str, Any]:
    """Sent on every call, so the server never gets to choose (§12)."""
    sampling = config["sampling"]
    options = {
        "temperature": sampling[role + "_temperature"],
        "num_ctx": sampling["context_length"],
    }
    if sampling.get("seed") is not None:
        options["seed"] = sampling["seed"]
    return options


def _post(url: str, payload: Dict[str, Any], timeout: float) -> Dict[str, Any]:
    response = httpx.post(url, json=payload, timeout=timeout)
    response.raise_for_status()
    return response.json()
