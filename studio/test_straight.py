import json
import pathlib
import sys

import pytest

sys.path[:0] = [str(pathlib.Path(__file__).resolve().parent),
              str(pathlib.Path(__file__).resolve().parent.parent)]
from straight import eligible_card
from repofuse.budget import Budget, BudgetExceeded
from repofuse.synthesize import recover_empty_glue


def card(**over):
    base = {"id": "model-integration-1", "title": "Typed inspector",
            "runtime": "python-wsgi", "dependencies": [], "external_services": []}
    base.update(over)
    return base


def test_first_buildable_card_is_chosen():
    chosen = eligible_card([
        card(id="skip", title="Needs a service", external_services=["smtp"]),
        card(id="deps", title="Needs a package", dependencies=["requests"]),
        card(id="other", title="Other runtime", runtime="node"),
        card(id="keep", title="Plain WSGI"),
        card(id="later", title="Also plain"),
    ])
    assert chosen["id"] == "keep"


def test_nothing_buildable_returns_none():
    assert eligible_card([card(dependencies=["x"]), {"runtime": "python-wsgi"}]) is None
    assert eligible_card(None) is None


def _repair_budget(tmp_path):
    envelope = tmp_path / "envelope.json"
    envelope.write_text(json.dumps({
        "max_calls": 5, "max_count_calls": 5,
        "max_input_tokens": 12000, "max_output_tokens": 4096,
        "max_total_input_tokens": 60000, "max_total_output_tokens": 20480,
    }))
    budget = Budget(str(tmp_path / "budget.json"), envelope_path=str(envelope))
    names = ["idea-suggest", "architecture-manifest", "glue-synthesis"]
    budget.state = {
        "calls": [{"step": name, "actual": {"input": 1, "output": 1}} for name in names],
        "count_calls": [{"step": name} for name in names],
        "reserved_input": 0, "reserved_output": 0,
        "actual_input": 3, "actual_output": 3,
    }
    return budget


def test_empty_glue_spends_the_one_repair(tmp_path, monkeypatch):
    calls = []

    def gated(step, messages, out_dir, budget, **kwargs):
        calls.append(step)
        source = (
            "def describe():\n"
            "    return {'title': 't', 'description': 'd', 'example': {}}\n"
            "def compute(payload):\n"
            "    if not isinstance(payload, dict):\n"
            "        raise ValueError('payload')\n"
            "    return {'ok': True}\n"
        )
        return {"content": json.dumps({"integration.py": source}),
                "model": "fixture", "usage": {}, "latency_ms": 1}, None

    monkeypatch.setattr("repofuse.synthesize.call_gated", gated)
    files, _response = recover_empty_glue(
        str(tmp_path), _repair_budget(tmp_path), {}, {}, {}, None)
    assert calls == ["syntax-repair"]
    assert set(files) == {"integration.py"}
    assert "def compute" in files["integration.py"]


def test_empty_glue_without_the_repair_slot_refuses(tmp_path):
    envelope = tmp_path / "envelope.json"
    envelope.write_text(json.dumps({"max_calls": 5, "max_count_calls": 5}))
    budget = Budget(str(tmp_path / "budget.json"), envelope_path=str(envelope))
    with pytest.raises(BudgetExceeded):
        recover_empty_glue(str(tmp_path), budget, {}, {}, {}, None)
