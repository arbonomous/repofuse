"""One bounded auto-heal round, under the same gated budget as synthesis.

Model-gated: without a key there is no heal and no pretend fix. Exactly ONE
round; a second failure is reported, not looped.
"""
from __future__ import annotations

import json
import os
import time

from . import model_api
from .budget import Budget, BudgetExceeded
from .synthesize import _extract_json, _write_files, call_gated
from .verify import verify_fused_app


def auto_heal(out_dir, first_result, env=None, attestation_path=None):
    fusion_dir = os.path.join(out_dir, "fused_app")
    if first_result.get("status") != "failed":
        return {"status": "not_attempted",
                "reason": f"verify status {first_result.get('status')}"}
    if not model_api.have_model_key(env):
        return {"status": "pending_no_key",
                "reason": "verify failed but no MODEL_API_KEY for heal"}
    generated = {}
    gen_dir = os.path.join(fusion_dir, "generated")
    for d in (gen_dir, fusion_dir):
        if not os.path.isdir(d):
            continue
        for name in os.listdir(d):
            full = os.path.join(d, name)
            if os.path.isfile(full) and name.endswith(".py"):
                rel = os.path.relpath(full, fusion_dir)
                generated[rel] = open(full, encoding="utf-8").read()
    ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    msgs = [
        {"role": "developer", "content":
            "You are the RepoFuse heal model. You receive generated files and "
            "the observed test failure output. Return a JSON object mapping "
            "NEW file names (suffix _fix.py) to corrected FULL contents. Fix "
            "only what the failure shows. Never invent APIs."},
        {"role": "user", "content": json.dumps({
            "task": "Fix the failing fused app. One correction round only.",
            "observed_stderr": first_result.get("stderr", "")[-3000:],
            "observed_stdout": first_result.get("stdout", "")[-2000:],
            "files": {k: v[:20000] for k, v in generated.items()},
        }, indent=2)},
    ]
    budget = Budget(os.path.join(out_dir, "budget.json"))
    try:
        resp, _ = call_gated("auto-heal", msgs, out_dir, budget, env=env)
    except (BudgetExceeded, model_api.ModelUnavailable,
            model_api.ModelCallError) as e:
        return {"status": "failed", "reason": f"{e.__class__.__name__}: {e}"}
    try:
        files = _extract_json(resp["content"])
    except ValueError as e:
        return {"status": "failed", "reason": f"heal output not JSON: {e}"}
    written = _write_files(fusion_dir, files, resp["model"], ts, slot="glue")
    second = verify_fused_app(fusion_dir, attestation_path=attestation_path)
    return {"status": "completed", "healed_files": written,
            "second_verify": second,
            "note": "exactly one heal round; result is observed, not asserted"}
