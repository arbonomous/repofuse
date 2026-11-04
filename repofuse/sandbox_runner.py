"""Trusted in-sandbox test runner. Copied into the scratch dir by the host;
generated code cannot modify it (vendor/generated slots are elsewhere and
writes are host-side exclusive-create).

Forgery resistance: the verdict is HMAC-signed with a one-time key delivered
through a pipe that is read and CLOSED before any test/glue code is imported.
A model-generated file that prints 'Ran 5 tests / OK' to stdout does not
produce a valid signed verdict. Residual, honestly documented: Python runs
tested code in-process, so deliberately adversarial code could introspect the
interpreter; the signed channel defeats output forgery, not all in-process
tampering.
"""
import hashlib
import hmac
import io
import json
import os
import sys
import unittest


def main():
    key_fd = int(sys.argv[1])
    module = sys.argv[2]
    key = b""
    while True:
        chunk = os.read(key_fd, 4096)
        if not chunk:
            break
        key += chunk
    os.close(key_fd)  # key channel closed BEFORE untrusted imports

    suite = unittest.TestLoader().loadTestsFromName(module)
    stream = io.StringIO()
    result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
    sys.stderr.write(stream.getvalue())
    verdict = {"ran": result.testsRun,
               "errors": len(result.errors),
               "failures": len(result.failures),
               "ok": bool(result.wasSuccessful())}
    body = json.dumps(verdict, sort_keys=True).encode()
    tag = hmac.new(key, body, hashlib.sha256).hexdigest()
    print("REPOFUSE-VERDICT " + tag + " " + body.decode())


if __name__ == "__main__":
    main()
