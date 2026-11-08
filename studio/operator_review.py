"""Record a review the operator confirmed on this local Studio page.

The server recomputes every binding. The request may only echo the
finding lines or digests this module just derived. Fail and unknown
verdicts cannot be recorded. Nothing here executes generated code or
contacts a model.
"""
import hashlib
import json
import pathlib
import tempfile

from review_exchange import RUN_ID, Refused, _binding, import_review


def finding_lines(verdict):
    if not isinstance(verdict, dict):
        raise Refused("No safety verdict on this run.")
    lines = []
    for repo in verdict.get("repos") or []:
        name = str(repo.get("repo") or "")
        static = repo.get("static") or {}
        for finding in static.get("findings") or []:
            lines.append("|".join((
                name,
                str(finding.get("file") or ""),
                str(finding.get("rule") or ""),
                str(finding.get("detail") or ""),
            )))
        advisory = repo.get("dependencies") or {}
        lines.append("|".join((
            name, "advisory",
            str(advisory.get("status") or ""),
            str(advisory.get("note") or ""),
        )))
    if not lines:
        raise Refused("Safety verdict has no repository lines to confirm.")
    return sorted(lines)


def _recordable(verdict):
    status = verdict.get("status")
    if status in ("fail", "unknown"):
        raise Refused(
            f"Safety verdict is {status}. A failed or unknown check "
            "cannot be recorded.")
    for repo in verdict.get("repos") or []:
        if repo.get("status") in ("fail", "unknown") or repo.get("blocking"):
            raise Refused(
                "A repository check failed or is unknown. Recording "
                "it would not let this build continue.")
    return status


def _reviewer(value):
    if not isinstance(value, str) or len(value.strip()) < 2 or len(value) > 120:
        raise Refused("Enter the name of the person who read this.")
    return value.strip()


def _write_record(studio_root, record):
    root = pathlib.Path(studio_root)
    if root.is_symlink():
        raise Refused("Studio root is a symlink.")
    with tempfile.NamedTemporaryFile(
            mode="w", prefix=".operator-review-", suffix=".json",
            dir=root, delete=False) as handle:
        json.dump(record, handle)
        path = pathlib.Path(handle.name)
    try:
        return path
    except Exception:
        path.unlink(missing_ok=True)
        raise


def record_input(studio_root, run, reviewer, findings):
    verdict = run.get("safety")
    _recordable(verdict)
    if findings != finding_lines(verdict):
        raise Refused("The confirmed findings do not match this run.")
    record = dict(_binding(run), reviewer=_reviewer(reviewer), note=(
        "Recorded on the local Studio page after these finding lines "
        "were shown. This does not approve execution, and it cannot "
        "clear a failed or unknown check."))
    path = _write_record(studio_root, record)
    try:
        return import_review(path, studio_root)
    finally:
        path.unlink(missing_ok=True)


def record_disclosure(studio_root, run_id, metas, reviewer, payload_sha256):
    if not RUN_ID.fullmatch(run_id):
        raise Refused("Invalid local run id.")
    from model_ideas import prepare
    from import_disclosure import import_disclosure
    _rows, _msgs, _payload, _raw, bound = prepare(metas, run_id)
    if payload_sha256 != bound.get("payload_sha256"):
        raise Refused("The confirmed request hash does not match the exact unsent metadata.")
    record = dict(bound, approved=True, reviewer=_reviewer(reviewer),
                  execution_approved=False)
    path = _write_record(studio_root, record)
    try:
        return import_disclosure(path, studio_root)
    finally:
        path.unlink(missing_ok=True)


def tree_digest(files):
    raw = json.dumps(files, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()


def record_source(studio_root, run, reviewer, tree_sha256):
    _recordable(run.get("safety"))
    if run.get("status") not in ("awaiting_review", "frontend_preflight_failed", "build_failed"):
        raise Refused("This run has no generated tree waiting for review.")
    from repofuse import gluereview
    rid = run.get("run_id") or ""
    app = pathlib.Path(studio_root) / "runs" / (rid + "-fusion") / "fused_app"
    if app.is_symlink() or not app.is_dir():
        raise Refused("Generated tree is not available.")
    if gluereview.execution_symlinks(str(app)):
        raise Refused("Symlinks invalidate source review.")
    files = {rel: gluereview._sha256(str(app / rel))
             for rel in gluereview.review_targets(str(app))}
    if tree_sha256 != tree_digest(files):
        raise Refused("The confirmed tree hash does not match the current bytes.")
    record = dict(_binding(run), reviewer=_reviewer(reviewer), note=(
        "Recorded on the local Studio page for the current generated "
        "and vendored bytes. This permits contained tests and serving "
        "only while those bytes still match."),
        whole_tree={"files": files})
    path = _write_record(studio_root, record)
    try:
        return import_review(path, studio_root)
    finally:
        path.unlink(missing_ok=True)


def generated_preview(app):
    """Text the operator can read. Vendored trees stay as hashes."""
    shown = {}
    root = pathlib.Path(app)
    for rel in ("generated/integration.py", "generated/app.py",
                "test_fused.py", "serving.json"):
        path = root / rel
        if not path.is_file() or path.is_symlink() or path.stat().st_size > 40000:
            continue
        shown[rel] = path.read_text(encoding="utf-8", errors="replace")
    return shown
