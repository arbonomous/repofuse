"""Append-only token/latency telemetry for model calls."""
from __future__ import annotations

import json
import os
import time


def log_call(path, *, step, model, usage, latency_ms, status):
    rec = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "step": step,
        "model": model,
        "usage": usage,
        "latency_ms": latency_ms,
        "status": status,
    }
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec) + "\n")
    return rec


def read_log(path):
    if not os.path.exists(path):
        return []
    out = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out
