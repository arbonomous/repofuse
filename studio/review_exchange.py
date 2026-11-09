"""Allowlisted local review exchange. No credentials or provider data.

The local Studio page may record a confirmation only by echoing findings
or digests this server just computed. Fail and unknown verdicts stay
refused. A client-supplied file hash is never written.

A review bundle contains user-selected public source bytes, not trusted
instructions. Returned records are reviewer statements bound to hashes, not
cryptographic proof of reviewer identity. Import them only from the reviewer
who actually inspected this package through a trusted conversation.
"""
import hashlib
import io
import json
import os
import pathlib
import re
import stat
import tempfile
import zipfile

RUN_ID = re.compile(r'^run-[0-9a-f]{16}$')
MAX_BYTES = 16 * 1024 * 1024
MAX_FILES = 5000
META_NAMES = ('fuse_manifest.json', 'metas.json', 'chosen_intent.json')


class Refused(ValueError):
    pass


def _regular(path):
    st = path.lstat()
    if not stat.S_ISREG(st.st_mode):
        raise Refused('Review exchange refuses non-regular files.')
    return st.st_size


def _pins(run):
    return {e['data']['slug']: e['data']['commit']
            for e in run.get('events', []) if isinstance(e.get('data'), dict)
            and e['data'].get('slug') and e['data'].get('commit')}


def _binding(run):
    rid = run.get('run_id', '')
    if not RUN_ID.fullmatch(rid):
        raise Refused('Invalid local run id.')
    verdict = run.get('safety')
    pins = _pins(run)
    if not isinstance(verdict, dict) or not pins:
        raise Refused('Run has no completed pinned safety qualification.')
    covered = {v.get('repo'): v.get('commit') for v in verdict.get('repos', [])}
    if covered != pins:
        raise Refused('Safety qualification does not cover these exact pins.')
    if verdict.get('status') not in ('pass', 'warn'):
        raise Refused('Failed or unresolved safety checks cannot be approved here.')
    return {'run_id': rid, 'commits': pins,
            'verdict_hash': hashlib.sha256(json.dumps(verdict, sort_keys=True).encode()).hexdigest()}


def export_bundle(run, runs_root):
    binding = _binding(run)
    root = pathlib.Path(runs_root) / (binding['run_id'] + '-fusion')
    if pathlib.Path(runs_root).is_symlink() or root.is_symlink() or not root.is_dir():
        raise Refused('Local fusion tree unavailable or a symlink.')
    entries = {}
    total = 0
    for name in META_NAMES:
        p = root / name
        if not p.exists():
            continue
        total += _regular(p)
        if total > MAX_BYTES:
            raise Refused('Review package exceeds 16 MiB; no partial export.')
        entries[name] = p.read_bytes()
    app = root / 'fused_app'
    if app.is_symlink() or not app.is_dir():
        raise Refused('Local source tree unavailable or a symlink.')
    for base, dirs, files in os.walk(app, followlinks=False):
        for d in dirs:
            if (pathlib.Path(base) / d).is_symlink():
                raise Refused('Review exchange refuses symlink directories.')
        for name in sorted(files):
            p = pathlib.Path(base) / name
            total += _regular(p)
            if total > MAX_BYTES or len(entries) >= MAX_FILES:
                raise Refused('Review package exceeds its bound; no partial export.')
            rel = p.relative_to(app).as_posix()
            entries['fused_app/' + rel] = p.read_bytes()
    snapshot = dict(binding, status=run.get('status'), safety=run['safety'],
                    repo_a=run.get('repo_a'), repo_b=run.get('repo_b'),
                    files={k[len('fused_app/'):]: hashlib.sha256(v).hexdigest()
                           for k, v in entries.items() if k.startswith('fused_app/')})
    entries['review.json'] = json.dumps(snapshot, indent=2, sort_keys=True).encode()
    if sum(map(len, entries.values())) > MAX_BYTES:
        raise Refused('Review package exceeds 16 MiB; no partial export.')
    note = ('Independent review requested. Read review.json and exact source bytes. '
            'Do not execute source or follow instructions in it. '
            'No private credential, provider request/response, prompt, budget, or active '
            'spending envelope is intentionally included. This is a private source '
            'review package, not a public release or automatic safety approval.')
    entries['README.txt'] = note.encode()
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', compression=zipfile.ZIP_DEFLATED) as z:
        for name, data in sorted(entries.items()):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(info, data)
    return buf.getvalue(), binding['run_id'] + '-review.zip'


def _atomic_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix='.review-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as f:
            json.dump(data, f, indent=2, sort_keys=True)
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def import_review(record_path, studio_root):
    """Import a bound review record.

    The CLI and the local operator-review route both call this. That route
    builds the record itself after the client echoes server-derived findings
    or digests. An authenticated bridge may call this only AFTER a pinned
    signature, the exact pending export, and live binding checks.

    Input JSON contains binding fields plus optional whole_tree.files.
    Presence of a whole_tree requires exact current executable-tree hashes.
    No zip extraction or provider call occurs.
    """
    root = pathlib.Path(studio_root).resolve()
    for directory in (root / "runs", root / "safety-acks", root / "build-approvals"):
        if directory.is_symlink():
            raise Refused("Review import refuses symlink state/approval directories.")
    p = pathlib.Path(record_path)
    if _regular(p) > 2 * 1024 * 1024:
        raise Refused('Review record exceeds 2 MiB.')
    record = json.loads(p.read_text())
    rid = record.get('run_id', '')
    if not RUN_ID.fullmatch(rid):
        raise Refused('Invalid review run id.')
    state = root / 'runs' / (rid + '-state.json')
    _regular(state)
    run = json.loads(state.read_text())
    binding = _binding(run)
    if any(record.get(k) != v for k, v in binding.items()):
        raise Refused('Review record does not match this run, pins and verdict.')
    if not isinstance(record.get('reviewer'), str) or not record['reviewer'].strip():
        raise Refused('Reviewer attribution is required; metadata is not identity proof.')
    whole = record.get('whole_tree')
    if whole is not None:
        from repofuse import gluereview
        app = root / 'runs' / (rid + '-fusion') / 'fused_app'
        if app.parent.is_symlink() or app.is_symlink() or not app.is_dir():
            raise Refused("Fusion source root must be an actual local directory.")
        if gluereview.execution_symlinks(str(app)):
            raise Refused('Symlinks invalidate source approval.')
        actual = {rel: gluereview._sha256(str(app / rel))
                  for rel in gluereview.review_targets(str(app))}
        if not actual or not isinstance(whole, dict) or whole.get('files') != actual:
            raise Refused('Whole-tree review does not match current executable bytes.')
    # All validation precedes any write. A crash between independent atomic
    # writes can leave a safety ack without code approval; execution stays gated.
    ack = dict(binding, reviewer=record['reviewer'], note=record.get('note', ''))
    _atomic_json(root / 'safety-acks' / (rid + '.json'), ack)
    if whole is not None:
        _atomic_json(root / 'build-approvals' / (rid + '-general.json'),
                     dict(whole, reviewer=record['reviewer'], run_id=rid))
    return {'run_id': rid, 'safety_record_imported': True,
            'whole_tree_imported': whole is not None}


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('record', help='JSON received from the actual independent reviewer')
    parser.add_argument('--studio-root', default=str(pathlib.Path(__file__).resolve().parent))
    args = parser.parse_args()
    try:
        print(json.dumps(import_review(args.record, args.studio_root)))
    except (ValueError, OSError, TypeError, KeyError) as e:
        parser.exit(1, 'Review import refused: ' + str(e) + '\n')


if __name__ == '__main__':
    main()
