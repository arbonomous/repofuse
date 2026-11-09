"""Save a short record of a stopped build for this machine.

The record is the run id, the two repository URLs, the status, and the
latest error sentence. It does not include source, prompts, or keys.
"""
import json
import os
import time

KINDS = ("error", "safety_blocked", "planning_refused", "blocked")
TEXT_LIMIT = 500


def summarize(run):
    if not isinstance(run, dict):
        raise ValueError("Run record must be an object.")
    events = [e for e in (run.get("events") or []) if isinstance(e, dict)]
    chosen = None
    for event in reversed(events):
        if event.get("kind") in KINDS:
            chosen = event
            break
    if chosen is None and events:
        chosen = events[-1]
    text = ""
    kind = ""
    stage = ""
    if chosen:
        text = str(chosen.get("text") or "")[:TEXT_LIMIT]
        kind = str(chosen.get("kind") or "")[:40]
        stage = str(chosen.get("stage") or "")[:40]
    safety = run.get("safety") if isinstance(run.get("safety"), dict) else {}
    repos = []
    for repo in safety.get("repos") or []:
        if isinstance(repo, dict):
            repos.append({"repo": str(repo.get("repo") or "")[:80],
                          "status": str(repo.get("status") or "")[:20]})
    return {
        "run_id": str(run.get("run_id") or "")[:40],
        "status": str(run.get("status") or "")[:40],
        "repo_a": str(run.get("repo_a") or "")[:200],
        "repo_b": str(run.get("repo_b") or "")[:200],
        "stage": stage,
        "kind": kind,
        "text": text,
        "safety_status": str(safety.get("status") or "")[:20],
        "repos": repos[:8],
        "ts": time.time(),
    }


def record(studio_root, run):
    """Write one JSON file and one inbox line. Same text is not repeated."""
    summary = summarize(run)
    if not summary["run_id"] or not summary["text"]:
        return None
    folder = os.path.join(studio_root, "relay")
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, summary["run_id"] + ".json")
    previous = ""
    if os.path.isfile(path):
        try:
            with open(path, encoding="utf-8") as handle:
                previous = json.load(handle).get("text") or ""
        except (OSError, ValueError):
            previous = ""
    if previous == summary["text"]:
        return path
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as handle:
        json.dump(summary, handle, indent=2)
    os.replace(tmp, path)
    with open(os.path.join(folder, "inbox.jsonl"), "a", encoding="utf-8") as handle:
        handle.write(json.dumps(summary) + "\n")
    return path
