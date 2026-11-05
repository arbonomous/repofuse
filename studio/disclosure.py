"""Disclosure-only gate for an exact bounded public metadata payload.

This never writes execution acknowledgments or approves source/dependencies.
An independent review record binds only the exact bytes to be sent to Meta.
"""
import hashlib
import json
import re

MAX_BYTES = 32000
# Conservative secret indicators, not proof that no secret exists.
SECRET_PATTERNS = (
    re.compile(r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----'),
    re.compile(r'\b(?:ghp_|github_pat_|sk_live_|sk_test_)[A-Za-z0-9_\-]{12,}'),
    re.compile(r'(?i)(?:api[_ -]?key|access[_ -]?token|password|client[_ -]?secret)\s*[:=]\s*[\'\"][A-Za-z0-9_\-]{16,}[\'\"]'),
)


class Refused(ValueError):
    pass


def canonical_payload(messages, model_payload):
    """Return exact send payload bytes. The caller supplies build_payload's
    full result, not a summaries-only approximation of the eventual request.
    """
    if not isinstance(messages,list) or model_payload.get('messages') != messages:
        raise Refused('Exact request messages do not match the disclosure preview.')
    data=json.dumps(model_payload).encode('utf-8')
    if len(data)>MAX_BYTES:
        raise Refused('Exact metadata request exceeds the disclosure size bound.')
    text=data.decode('ascii')
    if any(p.search(text) for p in SECRET_PATTERNS):
        raise Refused('Potential secret marker in proposed disclosure; no request sent.')
    if model_payload.get('model')!='muse-spark-1.3':
        raise Refused('Disclosure destination model differs from reviewed Meta run.')
    return data


def binding(run_id, rows, request_bytes):
    if not re.fullmatch(r'run-[0-9a-f]{16}',run_id):
        raise Refused('Invalid local run identifier.')
    if len(rows)!=2:
        raise Refused('Exactly two public evidence rows required.')
    pins={}
    for row in rows:
        if not re.fullmatch(r'https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+',row.get('url','')):
            raise Refused('Evidence source is not an exact public GitHub repository URL.')
        if not re.fullmatch(r'[0-9a-f]{40}',row.get('commit','')):
            raise Refused('Evidence commit is not pinned.')
        pins[row['repo']]=row['commit']
    if len(pins)!=2:
        raise Refused('Distinct repository identities required.')
    return {'kind':'public-metadata-disclosure-v1','run_id':run_id,
            'destination':'https://api.meta.ai/v1',
            'commits':pins,'payload_sha256':hashlib.sha256(request_bytes).hexdigest(),
            'payload_bytes':len(request_bytes)}


def check_review(record, expected):
    if not isinstance(record,dict) or any(record.get(k)!=v for k,v in expected.items()):
        raise Refused('Independent disclosure review is missing or does not match exact request bytes.')
    if record.get('approved') is not True or not record.get('reviewer'):
        raise Refused('Independent disclosure review has not approved this request.')
    # An execution ack cannot be laundered into this role, or vice versa.
    if record.get('execution_approved') is not False:
        raise Refused('Disclosure review must explicitly grant no execution authority.')
    return True
