# ahead_agent/causes/embeddings.py
# ─────────────────────────────────────────────
# PORTADO from the Python arm, with the endpoint and model taken from the
# profile instead of module constants, and httpx instead of requests.
# `_post`/`_get` are deliberately not shared with llm.py: llm._post is
# test_llm.py's monkeypatch seam, and causes/ must stay runnable on its own (§2).
# ─────────────────────────────────────────────

from __future__ import annotations

from typing import Any, Dict, List

import httpx


class EmbeddingError(RuntimeError):
    """No vector could be obtained. It is never replaced by another number."""


# ── Vectors ──────────────────────────────────


def get_embedding(config: Dict[str, Any], text: str) -> List[float]:
    """One vector. Tries /api/embed, then /api/embeddings on older Ollama."""
    url = config["server"]["ollama_url"].rstrip("/")
    model = config["models"]["embed"]
    timeout = config["server"]["request_timeout"]

    try:
        return _post(f"{url}/api/embed", {"model": model, "input": text}, timeout)["embeddings"][0]
    except (httpx.HTTPError, KeyError, IndexError, ValueError):
        pass

    try:
        return _post(f"{url}/api/embeddings", {"model": model, "prompt": text}, timeout)["embedding"]
    except (httpx.HTTPError, KeyError, ValueError) as error:
        raise EmbeddingError(f"{model}: {type(error).__name__}: {error}") from error


def get_embeddings(config: Dict[str, Any], texts: List[str]) -> List[List[float]]:
    """Sequential on purpose: a local Ollama serves them one at a time anyway."""
    return [get_embedding(config, text) for text in texts]


def embedding_model_available(config: Dict[str, Any]) -> bool:
    """Whether the embed model is loaded, so the caller can fall back knowingly."""
    url = config["server"]["ollama_url"].rstrip("/")
    model = config["models"]["embed"]
    
    try:
        listed = _get(f"{url}/api/tags", 5).get("models", [])
    except (httpx.HTTPError, ValueError):
        return False
    return any(str(entry.get("name", "")).startswith(model) for entry in listed)


# ── Talking to the server ────────────────────


def _post(url: str, payload: Dict[str, Any], timeout: float) -> Dict[str, Any]:
    """One POST, raising on anything that is not a 2xx."""
    response = httpx.post(url, json=payload, timeout=timeout)
    response.raise_for_status()
    return response.json()


def _get(url: str, timeout: float) -> Dict[str, Any]:
    """One GET, raising on anything that is not a 2xx."""
    response = httpx.get(url, timeout=timeout)
    response.raise_for_status()
    return response.json()
