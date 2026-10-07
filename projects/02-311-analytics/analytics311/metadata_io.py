"""Bounded accommodation for Windows reader/atomic-replacement sharing races."""
import errno
import os
import time


def retry_metadata_io(operation):
    """Retry only Windows access/sharing denials, for at most 225 ms of sleeps.

    Ordinary Windows file opens can briefly deny concurrent rename or open while
    another process reads/replaces JSON metadata. The CRT can report errno EACCES
    without a winerror; MoveFileEx reports access denied or sharing violations.
    Persistent permissions failures still raise after eight attempts. This is not
    a general I/O retry policy, and blocking OS calls can exceed the sleep budget.
    """
    for delay in (.005, .01, .02, .04, .05, .05, .05, None):
        try:
            return operation()
        except PermissionError as exc:
            if (os.name != "nt" or exc.errno != errno.EACCES
                    or getattr(exc, "winerror", None) not in (None, 5, 32, 33)
                    or delay is None):
                raise
            time.sleep(delay)
