"""Apply an operation's remaining time to each individual local HTTP call."""
from contextlib import contextmanager

from .records import DomainError


@contextmanager
def call_allowance(client, remaining_seconds):
    if remaining_seconds <= 0:
        raise DomainError("model_budget_exhausted", "No execution allowance remains; no new model call dispatched")
    original = getattr(client, "timeout", None)
    client.timeout = min(original, remaining_seconds) if original is not None else remaining_seconds
    try:
        yield
    finally:
        if original is None:
            del client.timeout
        else:
            client.timeout = original
