"""Client for Meta Model API (OpenAI-compatible chat completions).

Verified against dev.meta.ai docs (2026-11-03):
- Base URL: https://api.meta.ai/v1
- Auth: Bearer token in MODEL_API_KEY
- Models: muse-spark-1.3 (agentic/coding, 1M ctx). There is no
  "muse-code-1.0" API model; Muse Code is a CLI agent on Muse Spark.
Sources: https://dev.meta.ai/docs/models, https://dev.meta.ai/docs/quickstart

Transport hardening: endpoint host pinned to api.meta.ai, redirects REFUSED
(a redirect could forward the Bearer token to an unexpected host), response
and error bodies read with byte caps, elapsed time capped by timeout. The
key is read from the environment and never written to disk or logs.
"""
from __future__ import annotations

import json
import os
import time
import urllib.request
import urllib.error
import urllib.parse
import urllib.response

DEFAULT_BASE_URL = "https://api.meta.ai/v1"
COUNT_TOKENS_URL = "https://api.meta.ai/v1/messages/count_tokens"
ALLOWED_HOST = "api.meta.ai"
DEFAULT_MODEL = "muse-spark-1.3"
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
MAX_ERROR_BYTES = 4096


class ModelUnavailable(RuntimeError):
    """No usable credentials. Never fabricate model output."""


class ModelCallError(RuntimeError):
    def __init__(self, message, status=None, body_excerpt=None):
        super().__init__(message)
        self.status = status
        self.body_excerpt = body_excerpt


def have_model_key(env=None):
    env = os.environ if env is None else env
    return bool(env.get("MODEL_API_KEY") or env.get("META_API_KEY"))


def _api_key(env=None):
    env = os.environ if env is None else env
    return env.get("MODEL_API_KEY") or env.get("META_API_KEY")


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None  # any redirect becomes an HTTPError; never follow


_OPENER = urllib.request.build_opener(_NoRedirect)


def _post(url, payload, key, timeout):
    host = urllib.parse.urlparse(url).netloc
    if host != ALLOWED_HOST:
        raise ModelCallError(f"refused: endpoint host {host!r} is not "
                             f"{ALLOWED_HOST!r}")
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": "Bearer " + key,
                 "Content-Type": "application/json"},
        method="POST")
    try:
        with _OPENER.open(req, timeout=timeout) as resp:
            raw = resp.read(MAX_RESPONSE_BYTES + 1)
    except urllib.error.HTTPError as e:
        excerpt = ""
        try:
            excerpt = e.read(MAX_ERROR_BYTES).decode("utf-8", "replace")
            excerpt = excerpt.replace(key, "[redacted]")  # defensive
        except Exception:
            pass
        raise ModelCallError(f"Model API HTTP {e.code}", status=e.code,
                             body_excerpt=excerpt)
    except urllib.error.URLError as e:
        raise ModelCallError(f"Model API connection failed: {e.reason}")
    if len(raw) > MAX_RESPONSE_BYTES:
        raise ModelCallError("Model API response exceeds byte cap")
    try:
        return json.loads(raw.decode("utf-8"))
    except ValueError as e:
        raise ModelCallError(f"Model API returned non-JSON: {e}")


def count_tokens(messages, model=DEFAULT_MODEL, timeout=30, env=None):
    """Provider-measured input token count. Returns int or None.

    None means unavailable/unsupported/unparseable: the caller on a charged
    path must REFUSE, not estimate.
    """
    key = _api_key(env)
    if not key:
        return None
    payload = {"model": model, "messages": messages, "max_tokens": 1}
    try:
        body = _post(COUNT_TOKENS_URL, payload, key, timeout)
    except ModelCallError:
        return None
    for field in ("input_tokens", "tokens", "count"):
        if isinstance(body.get(field), int) and body[field] >= 0:
            return body[field]
    return None


def chat_completion(messages, model=DEFAULT_MODEL, max_tokens=4096,
                    timeout=60, base_url=DEFAULT_BASE_URL, env=None,
                    reasoning_effort=None, response_format=None):
    """One measured, capped chat completion. No retries, no redirects.

    max_tokens is clamped to the caller-visible hard cap by budget.py; this
    function additionally refuses values above 4096.

    Optional documented request controls (dev.meta.ai/docs/reasoning and
    /docs/structured-output), passed through verbatim when set:
    - reasoning_effort: top-level Chat Completions parameter; muse-spark
      always reasons ("none" returns HTTP 400), reasoning tokens share the
      max_tokens budget and billed output.
    - response_format: {"type": "json_schema", "json_schema": {...}} for
      schema-constrained decoding, or {"type": "json_object"} for
      valid-JSON-only mode (NOT schema-constrained - do not conflate).
    """
    key = _api_key(env)
    if not key:
        raise ModelUnavailable(
            "MODEL_API_KEY (or META_API_KEY) is not set; model call refused.")
    if max_tokens > 4096:
        raise ModelCallError(f"max_tokens {max_tokens} exceeds hard cap 4096")
    payload = {"model": model, "messages": messages, "max_tokens": max_tokens}
    if reasoning_effort is not None:
        payload["reasoning_effort"] = reasoning_effort
    if response_format is not None:
        payload["response_format"] = response_format
    started = time.monotonic()
    body = _post(base_url.rstrip("/") + "/chat/completions", payload, key,
                 timeout)
    latency_ms = int((time.monotonic() - started) * 1000)
    choices = body.get("choices") or []
    content = ""
    finish_reason = None
    if choices:
        content = (choices[0].get("message") or {}).get("content") or ""
        finish_reason = choices[0].get("finish_reason")
    return {
        "content": content,
        "model": body.get("model", model),
        "usage": body.get("usage") or {},
        "latency_ms": latency_ms,
        "finish_reason": finish_reason,
    }
