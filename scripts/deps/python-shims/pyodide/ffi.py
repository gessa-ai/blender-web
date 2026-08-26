# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later
#
# Import-shim for `pyodide.ffi` (Pyodide's foreign-function interface). NOT an
# FFI. Full rationale in the sibling top-level js.py shim.
#
# Covers EXACTLY the names urllib3 2.4.0's emscripten contrib imports at module
# load (contrib/emscripten/fetch.py:46-51): JsArray, JsException, JsProxy,
# to_js.
#
# DELIBERATELY ABSENT: run_sync / can_run_sync. fetch.py imports those lazily
# inside try/except ImportError (fetch.py:660 and :689); has_jspi() treats the
# ImportError as "JSPI unavailable" and returns False — which is the truth
# here. Defining them would falsely advertise a JSPI call bridge and route
# requests into send_jspi_request, deep into raise-on-use territory, instead of
# the clean has_jspi()==False path.
#
# JsProxy/JsArray exist for annotation and isinstance() use only (fetch.py has
# `from __future__ import annotations`, so its annotations never evaluate;
# nothing instantiates them at import). JsException must be a real exception
# type so runtime `except JsException:` clauses stay syntactically and
# semantically valid. to_js raises on use. Deferral recorded in
# ledger/deferred.json id=emscripten-network-transport.

_DEFERRED = (
    "blender-web 'pyodide.ffi' shim: no JavaScript FFI exists — this module only "
    "satisfies urllib3's emscripten import-time needs; Python-level networking is "
    "deferred (ledger/deferred.json id=emscripten-network-transport)."
)


class JsProxy:
    """Stand-in for pyodide.ffi.JsProxy (annotations/isinstance only)."""

    def __init__(self, *args, **kwargs):
        raise NotImplementedError(_DEFERRED)


class JsArray(JsProxy):
    """Stand-in for pyodide.ffi.JsArray (annotations/isinstance only)."""


class JsException(Exception):
    """Stand-in for pyodide.ffi.JsException (keeps `except JsException:` valid)."""


def to_js(*args, **kwargs):
    raise NotImplementedError(_DEFERRED)
