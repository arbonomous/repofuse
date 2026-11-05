"""Ephemeral local Studio credentials and one-shot run arming.

This module performs no network calls and grants no account authority.
Keys are never serialized, returned by status, or put in process environment.
The caller must authenticate local UI requests and check safety before consume.
"""
import threading

ENVELOPE = {
    "max_calls": 5, "max_count_calls": 5,
    "max_input_tokens": 12000, "max_output_tokens": 4096,
    "max_total_input_tokens": 60000, "max_total_output_tokens": 20480,
}


class Refused(ValueError):
    pass


class LocalSession:
    def __init__(self):
        self._lock = threading.Lock()
        self._key = None
        self._armed = None
        self._consumed = set()
        self._continuations = set()
        self._continuation_eligible = set()

    def connect(self, key):
        if not isinstance(key, str) or not 12 <= len(key) <= 4096:
            raise Refused("Enter a valid Meta API key in this local field.")
        if any(c.isspace() for c in key) or any(ord(c) < 33 or ord(c) > 126 for c in key):
            raise Refused("The key must contain printable characters without spaces.")
        with self._lock:
            self._key = key
            self._armed = None
            self._continuation_eligible.clear()
        return self.status()

    def disconnect(self):
        with self._lock:
            self._key = None
            self._armed = None
            self._continuation_eligible.clear()
        return self.status()

    def status(self):
        with self._lock:
            return {"connected": self._key is not None,
                    "armed_run": self._armed,
                    "limits": dict(ENVELOPE),
                    "storage": "Studio process memory only; cleared on restart"}

    def arm(self, run_id, *, confirmed_public_inputs, confirmed_credit_review):
        if confirmed_public_inputs is not True or confirmed_credit_review is not True:
            raise Refused("Confirm public inputs and current promo-credit review first.")
        with self._lock:
            if self._key is None:
                raise Refused("Connect Meta locally before arming this run.")
            if run_id in self._consumed:
                raise Refused("This run already consumed its one-shot arming; no retries.")
            if self._armed is not None and self._armed != run_id:
                raise Refused("Another run is armed. Disconnect to cancel it first.")
            self._armed = run_id
        return self.status()

    def consume(self, run_id):
        with self._lock:
            if self._key is None or self._armed != run_id:
                raise Refused("This run is not armed for local generation.")
            if run_id in self._consumed:
                raise Refused("One-shot run arming already consumed; no retries.")
            self._armed = None
            self._consumed.add(run_id)
            self._continuation_eligible.add(run_id)
            # Used only as the explicit env argument of the model client.
            return {"MODEL_API_KEY": self._key}, dict(ENVELOPE)

    def continue_planned_build(self, run_id):
        """Exactly one continuation of the SAME armed run, after caller
        verifies committed idea ledger and all execution/build safety gates.
        No new arming, key changes or budget widening is authorized here.
        """
        with self._lock:
            if (self._key is None or run_id not in self._continuation_eligible
                    or run_id in self._continuations):
                raise Refused("No unused same-session planning continuation exists.")
            self._continuations.add(run_id)
            return {"MODEL_API_KEY": self._key}
