"""Single-instance guard.

On Windows a named kernel mutex is the simplest cross-process lock: the first
process creates it; any later process that creates the same name gets
ERROR_ALREADY_EXISTS. Non-Windows platforms (dev machines) are not guarded.
"""

from __future__ import annotations

import logging
import sys

log = logging.getLogger("dekate.autobiometrik")

# Keep created handles referenced for the process lifetime so the OS holds the
# mutex until exit.
_handles: list[int] = []

_ERROR_ALREADY_EXISTS = 183


def acquire(name: str) -> bool:
    """True if this process now owns the lock; False if already held elsewhere."""
    if sys.platform != "win32":
        return True

    import ctypes

    kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
    handle = kernel32.CreateMutexW(None, False, name)
    last_error = kernel32.GetLastError()

    if not handle:
        # Could not create the mutex at all — don't block startup over it.
        log.warning("single-instance mutex could not be created (err=%s)", last_error)
        return True

    if last_error == _ERROR_ALREADY_EXISTS:
        return False

    _handles.append(handle)
    return True
