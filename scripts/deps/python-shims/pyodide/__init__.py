# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later
#
# Import-shim package for the Pyodide runtime namespace. Exists solely so
# `from pyodide.ffi import ...` (urllib3 2.4.0's emscripten contrib,
# contrib/emscripten/fetch.py:46-51) resolves on our non-Pyodide browser
# CPython. See pyodide/ffi.py and the sibling top-level js.py for the full
# rationale; deferral recorded in ledger/deferred.json
# id=emscripten-network-transport.
