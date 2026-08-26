# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later
#
# Single-process browser shim for CPython's `_multiprocessing` C extension.
#
# WHY THIS EXISTS
# ---------------
# The native `_multiprocessing` module (Modules/_multiprocessing/semaphore.c)
# implements `SemLock` on POSIX *named* semaphores: sem_open / sem_close /
# sem_unlink / sem_getvalue / sem_timedwait. Emscripten only provides those
# symbols in its `-pthread` libc variant; our libpython is built single-threaded
# for the browser (ADR-001: `--with-emscripten-target=browser`, no
# __EMSCRIPTEN_PTHREADS__), so those symbols are UNDEFINED at link and CPython's
# configure correctly detects `ac_cv_func_sem_unlink=no` and drops the module.
# `_multiprocessing` is therefore genuinely unbuildable in our config — not a
# disabled optional, an unsupported one.
#
# Pyodide (the emscripten-CPython precedent) ships no `_multiprocessing` at all;
# its ecosystem answer is "patch the *consumer* to make the import optional".
# Our consumer is Blender's pinned bl_pkg addon (upstream, read-only): its
# register path imports `multiprocessing.synchronize`
# (addons_core/bl_pkg -> _bpy_internal/http/downloader.py:49
#  `from multiprocessing.synchronize import Event`), whose module top does
# `from _multiprocessing import SemLock, sem_unlink`. With the module absent that
# raises, bl_pkg register fails, and Blender pops the asset-library recovery
# dialog on boot — which pollutes the M4 first-pixels golden. We cannot patch
# bl_pkg, so we supply the missing module here instead.
#
# WHAT THIS IS
# ------------
# A faithful, single-process degradation: in a one-process runtime a
# "multiprocessing" semaphore IS a threading semaphore (exactly what
# `multiprocessing.dummy` assumes). SemLock is backed by threading primitives,
# so acquire/release/context-manager use is genuinely correct for the one
# process; it is not a raise-on-use stub. `name` is None (a thread-backed
# semaphore has no OS name), which makes `multiprocessing.synchronize` skip the
# resource_tracker / `_posixshmem` path that would otherwise need another absent
# C extension. Cross-process pickling (`__getstate__`/`_rebuild`) cannot occur
# with a single process, so those paths are best-effort and never exercised.
#
# Interface mirrors Modules/_multiprocessing/semaphore.c @ CPython 3.13.13
# (SemLock: kind/value/maxvalue/name/unlink ctor; acquire/release/_get_value/
# _count/_is_mine/_is_zero/_after_fork/_rebuild; SEM_VALUE_MAX class attr).

import threading
import time as _time

# Matches multiprocessing.synchronize: RECURSIVE_MUTEX, SEMAPHORE = range(2)
RECURSIVE_MUTEX = 0
SEMAPHORE = 1


class SemLock:
    """Thread-backed stand-in for `_multiprocessing.SemLock` (single process)."""

    # POSIX SEM_VALUE_MAX on the native (glibc) oracle is INT_MAX.
    SEM_VALUE_MAX = 2 ** 31 - 1

    def __init__(self, kind, value, maxvalue, name, unlink):
        self.kind = kind
        self.maxvalue = maxvalue
        # No OS-named semaphore backs us -> None so synchronize.py skips
        # resource_tracker registration (which would import _posixshmem).
        self.name = None
        self.handle = None
        self._cond = threading.Condition(threading.Lock())
        self._value = value
        self._owner = None          # thread ident currently holding the lock
        self._rcount = 0            # (recursive) acquisition depth by _owner

    # -- acquisition -------------------------------------------------------
    def acquire(self, block=True, timeout=None):
        tid = threading.get_ident()
        with self._cond:
            if self.kind == RECURSIVE_MUTEX and self._owner == tid:
                self._rcount += 1
                return True
            deadline = None if timeout is None else _time.monotonic() + timeout
            while self._value == 0:
                if not block:
                    return False
                remaining = None
                if deadline is not None:
                    remaining = deadline - _time.monotonic()
                    if remaining <= 0:
                        return False
                self._cond.wait(remaining)
                if self._value == 0 and deadline is not None \
                        and deadline - _time.monotonic() <= 0:
                    return False
            self._value -= 1
            self._owner = tid
            self._rcount = 1
            return True

    def release(self):
        tid = threading.get_ident()
        with self._cond:
            if self.kind == RECURSIVE_MUTEX:
                if self._owner != tid:
                    raise AssertionError(
                        "attempt to release recursive lock not owned by thread")
                self._rcount -= 1
                if self._rcount > 0:
                    return
                self._owner = None
                self._value += 1
                self._cond.notify()
                return
            # SEMAPHORE: refuse to exceed maxvalue, like the native impl.
            if self._value >= self.maxvalue:
                raise ValueError("semaphore or lock released too many times")
            self._value += 1
            self._owner = None
            self._rcount = 0
            self._cond.notify()

    # -- context manager ---------------------------------------------------
    def __enter__(self):
        return self.acquire()

    def __exit__(self, *args):
        return self.release()

    # -- introspection (used by synchronize.py __repr__ / Condition) -------
    def _get_value(self):
        return self._value

    def _count(self):
        return self._rcount

    def _is_mine(self):
        return self._owner == threading.get_ident() and self._rcount > 0

    def _is_zero(self):
        return self._value == 0

    def _after_fork(self):
        # No fork in a browser process; nothing to re-arm.
        pass

    # -- pickling across processes (never happens single-process) ----------
    @staticmethod
    def _rebuild(handle, kind, maxvalue, name):
        return SemLock(kind, 1, maxvalue, name, False)


def sem_unlink(name):
    # Thread-backed semaphores have no OS name to remove.
    pass
