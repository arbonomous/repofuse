import json
import pathlib
import sys

sys.path[:0] = [str(pathlib.Path(__file__).resolve().parent),
                str(pathlib.Path(__file__).resolve().parent.parent)]
import relay
from test_model_ideas import m, metas


def test_record_saves_the_error_sentence_once(tmp_path):
    run = {"run_id": "run-0123456789abcdef", "status": "failed",
           "repo_a": "https://github.com/hummingbot/hummingbot",
           "repo_b": "https://github.com/drakkar-software/octobot",
           "events": [{"kind": "error", "stage": "error",
                       "text": "pipeline error: Static evidence exceeds the bounded analysis request."}]}
    first = relay.record(tmp_path, run)
    relay.record(tmp_path, run)
    saved = json.loads(pathlib.Path(first).read_text())
    assert saved["text"].endswith("bounded analysis request.")
    assert saved["repo_a"].endswith("/hummingbot")
    assert "events" not in saved
    lines = (tmp_path / "relay" / "inbox.jsonl").read_text().strip().splitlines()
    assert len(lines) == 1


def test_large_repository_evidence_is_shortened():
    data = metas()
    for name in data:
        data[name]["readme_excerpt"] = "R" * 1600
        data[name]["tree"] = [("dir/" * 20) + f"f{i}.py" for i in range(50)]
        data[name]["analysis"]["exports"] = [f"Name{i}" for i in range(36)]
        data[name]["analysis"]["dependencies"] = {
            f"dep{i}": {"spec": ">=1.2.3", "via": "pyproject.toml"} for i in range(45)}
        data[name]["analysis"]["api_evidence"] = {
            "status": "static_declarations_only",
            "exports": [{"module": "pkg.mod", "name": f"Name{i}", "kind": "function",
                         "signature": "x" * 180, "file": "pkg/mod.py"} for i in range(36)]}
    rows = m.evidence(data)
    assert len(json.dumps(rows)) <= m.MAX_EVIDENCE_CHARS
    assert rows[0]["exports_sample"]
    assert all(name.startswith("Name") for name in rows[0]["exports_sample"])
