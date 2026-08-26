# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later
#
# Import-shim for Pyodide's `js` JavaScript-bridge module. NOT a bridge.
#
# WHY THIS EXISTS
# ---------------
# urllib3 2.4.0 hard-codes a Pyodide assumption: on any interpreter reporting
# `sys.platform == 'emscripten'` (which our browser CPython correctly does),
# urllib3/__init__.py:208-211 unconditionally runs `inject_into_urllib3()`,
# whose import chain (contrib/emscripten/fetch.py:45-46) executes `import js`
# and `from pyodide.ffi import JsArray, JsException, JsProxy, to_js`. Those are
# modules the Pyodide RUNTIME provides, not any wheel; our non-Pyodide CPython
# ships neither, so `import urllib3` (hence `import requests`, hence bl_pkg
# register via _bpy_internal/http/downloader.py:53-55) raises
# ModuleNotFoundError('js') at register on the wasm build, popping the
# asset-library recovery dialog (M4 first-pixels golden pollution). Desktop
# Blender never reaches the branch (`sys.platform` is never 'emscripten'
# there), so there is no native precedent to mirror — this is a web-only seam.
#
# WHAT THIS IS (and is NOT)
# -------------------------
# An empty namespace with a raise-on-use `__getattr__` — exactly enough for
# urllib3's import-time environment probes, which are pure hasattr() sniffs
# (fetch.py:411-441: is_worker_available -> hasattr(js,'Worker') and
# hasattr(js,'Blob'); is_cross_origin_isolated; is_in_node;
# is_in_browser_main_thread). hasattr() turns our AttributeError into False,
# every probe reports "environment lacks it", so urllib3 selects its
# no-streaming fallback at import (`_fetcher = None`, fetch.py:433-441) and
# spawns no workers. Import and register complete; NETWORKING DOES NOT WORK.
# Any path that actually touches the bridge (js.XMLHttpRequest in
# send_request, `from js import console` in the warning helpers, ...) raises
# the loud error below instead of silently pretending.
#
# Unlike the sibling `_multiprocessing.py` shim (genuinely functional for a
# single process), this is an HONEST DEFERRAL: recorded in
# ledger/deferred.json id=emscripten-network-transport. The real fix is a
# browser fetch transport backing this namespace (option B in
# notes/python-emcc605-probe.md "THE NEXT WALL"), a later platform_web feature.


import sys as _sys


class _Console:
    """Log-only stand-in for the JS console (NOT a bridge).

    urllib3's warning helpers do `from js import console` (fetch.py:496). A
    from-import that fails via module __getattr__ gets rewritten by CPython
    into a bare "ImportError: cannot import name 'console'", swallowing the
    descriptive deferral message below — so the one attribute reached on the
    honest fallback path is provided for real, routed to stderr. Everything
    else stays raise-on-use.
    """

    @staticmethod
    def _emit(*args):
        print("[js.console]", *args, file=_sys.stderr)

    log = warn = error = info = debug = _emit


console = _Console()


def __getattr__(name: str):
    raise AttributeError(
        f"blender-web 'js' shim: attribute {name!r} is unavailable — this module "
        "only satisfies urllib3's emscripten import-time probes; there is no "
        "JavaScript bridge and no Python-level network transport yet (deferred: "
        "ledger/deferred.json id=emscripten-network-transport)."
    )
