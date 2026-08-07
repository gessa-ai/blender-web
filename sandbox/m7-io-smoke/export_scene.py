# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later
#
# M7-io smoke: export the factory-startup default scene to OBJ (native C++
# wm.obj_export) and glTF-binary (python addon io_scene_gltf2, export_scene.gltf).
# Run IDENTICALLY on the wasm node binary and the native pin oracle so the two
# outputs are directly comparable. Output paths come from env; prints tagged
# lines. No new deps (numpy already present for the gltf addon).
import bpy, os, sys, addon_utils

# --- Bring-up shim: absent `_ctypes` C-extension in the wasm CPython payload -
# The glTF addon unconditionally imports its draco-compression module at
# execute() time (export.py:14 -> draco.py:5 `from ctypes import *`), and
# ctypes/__init__.py needs the `_ctypes` C-extension, which is not compiled into
# the wasm python. draco/meshopt only *use* ctypes inside functions that the
# default (uncompressed) GLB export never calls, so satisfying the *import* is
# enough to run the real, unmodified export code path. We inject a stub `ctypes`
# ONLY when the real one cannot import (native oracle keeps its real ctypes, so
# the same script runs on both sides). This shims an optional compression
# backend's import; it does NOT fake the export result — the produced .glb is
# validated against the native oracle. Proper fix: build `_ctypes` into the
# payload, or make the addon's draco import lazy (upstream, out of scope here).
try:
    import ctypes  # noqa: F401
    _CTYPES_SHIM = False
except Exception:
    import types
    class _Stub:  # placeholder for any ctypes symbol touched at import time
        def __init__(self, *a, **k):
            pass
    def _mk(name):
        m = types.ModuleType(name)
        m.__all__ = []
        m.__getattr__ = lambda _n: _Stub  # explicit `from ctypes import X`
        return m
    sys.modules["_ctypes"] = _mk("_ctypes")
    sys.modules["ctypes"] = _mk("ctypes")
    _CTYPES_SHIM = True
print("CTYPES_SHIM", _CTYPES_SHIM)
sys.stdout.flush()

obj_path = os.environ["M7_OBJ"]
glb_path = os.environ["M7_GLB"]

# Source mesh stats (pre-export, from the live scene) for the round-trip check.
cube = bpy.data.objects["Cube"]
me = cube.data
print("SRC_MESH Cube verts=%d edges=%d polys=%d loops=%d"
      % (len(me.vertices), len(me.edges), len(me.polygons), len(me.loops)))
sys.stdout.flush()

# --- OBJ (native C++ exporter, WITH_IO_WAVEFRONT_OBJ) -----------------------
try:
    bpy.ops.wm.obj_export(filepath=obj_path, export_selected_objects=False,
                          apply_modifiers=True)
    print("OBJ_EXPORT_OK", obj_path, os.path.getsize(obj_path))
except Exception as e:
    print("OBJ_EXPORT_FAIL", repr(e))
sys.stdout.flush()

# --- glTF-binary (python addon io_scene_gltf2) ------------------------------
# Ensure the addon is enabled (addons_core auto-enables under factory-startup,
# but enable defensively so the recipe is explicit and portable).
try:
    ok = addon_utils.check("io_scene_gltf2")[1]
    if not ok:
        addon_utils.enable("io_scene_gltf2", default_set=True, persistent=True)
    print("GLTF_ADDON_ENABLED", addon_utils.check("io_scene_gltf2")[1])
except Exception as e:
    print("GLTF_ADDON_ENABLE_FAIL", repr(e))
sys.stdout.flush()

# Workaround an upstream platform-detection bug the wasm target exposes:
# library.dll_path() maps only win32/linux/darwin, so on sys.platform=='emscripten'
# it returns None and dll_exists() dereferences None.absolute() (library.py:48).
# The correct wasm answer is that draco/meshopt native compression bridges are
# unavailable (no bridge .so, no libffi), so we assert that fact directly on the
# addon's cached availability flags. Only applied on platforms outside the
# upstream map (the native oracle keeps its real, working detection).
if sys.platform not in ("win32", "linux", "darwin"):
    import io_scene_gltf2 as _gltf
    _gltf.is_draco_available.draco_exists = False
    _gltf.is_meshopt_available.meshopt_exists = False
    print("GLTF_COMPRESSION_UNAVAILABLE draco=False meshopt=False (wasm)")
    sys.stdout.flush()

try:
    bpy.ops.export_scene.gltf(filepath=glb_path, export_format='GLB',
                              use_selection=False)
    print("GLTF_EXPORT_OK", glb_path, os.path.getsize(glb_path))
except Exception as e:
    print("GLTF_EXPORT_FAIL", repr(e))
sys.stdout.flush()
