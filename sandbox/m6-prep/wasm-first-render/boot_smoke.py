# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later
#
# M6 boot smoke: confirm the Cycles-enabled wasm node binary boots bpy and that
# CYCLES registers as a render engine (the M6 step-2 gate). Prints tagged lines.
import bpy, os, sys

print("BPY_OK", bpy.app.version_string, len(bpy.data.objects))
sys.stdout.flush()

# _cycles is a compiled builtin under WITH_CYCLES; prove it imports.
try:
    import _cycles
    print("CYCLES_BUILTIN_OK", hasattr(_cycles, "init"))
except Exception as e:
    print("CYCLES_BUILTIN_FAIL", repr(e))
sys.stdout.flush()

# Register the staged cycles addon (source tree lacks addons_core/cycles).
parent = os.environ.get("M6_CYCLES_ADDON_PARENT")
if parent and parent not in sys.path:
    sys.path.insert(0, parent)
try:
    import cycles
    cycles.register()
    print("CYCLES_ADDON_REGISTER_OK")
except Exception as e:
    print("CYCLES_ADDON_REGISTER_FAIL", repr(e))
sys.stdout.flush()

# The gate: engine assignment must succeed.
try:
    bpy.context.scene.render.engine = 'CYCLES'
    print("CYCLES_ENGINE_SET_OK", bpy.context.scene.render.engine)
except Exception as e:
    print("CYCLES_ENGINE_SET_FAIL", repr(e))
sys.stdout.flush()
