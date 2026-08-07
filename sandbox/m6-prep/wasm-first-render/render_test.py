# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later
#
# M6 Cycles suite — per-test wasm render driver (ONE BLEND PER node INVOCATION).
#
# Weans the Cycles-CPU render subset off cycles_render_tests.py, which spawns
# Blender subprocesses + multiprocessing (unavailable in single-process wasm
# python). The host runner (run_wasm_cycles.sh) drives one node invocation per
# test blend; this script renders frame 1 of the already-loaded blend on
# Cycles-CPU with the blend's OWN scene settings (samples/resolution/seed are
# NOT overridden — parity requires the exact settings the committed golden was
# rendered with; the framework's get_arguments() likewise never overrides them).
#
# Invocation (from run_wasm_cycles.sh), blend loaded as positional arg first:
#   node blender.js --background --factory-startup <blend> --python render_test.py
#   env: M6_OUT_BASE (output path prefix; frame 1 -> <base>0001.png),
#        M6_CYCLES_ADDON_PARENT (staged cycles addon parent dir),
#        M6_THREADS (fixed CPU thread count; <=0 => auto).
import bpy
import os
import sys

base = os.environ["M6_OUT_BASE"]


def ensure_cycles():
    # Source-tree boot (BLENDER_SYSTEM_RESOURCES=upstream) lacks
    # scripts/addons_core/cycles (copied only at install time), so the CYCLES
    # engine is unregistered until we register the staged addon by hand. The
    # _cycles C module is a builtin (inittab, WITH_CYCLES) so import works.
    scene = bpy.context.scene
    try:
        scene.render.engine = 'CYCLES'
        return "preregistered"
    except TypeError:
        pass
    parent = os.environ.get("M6_CYCLES_ADDON_PARENT")
    if parent and parent not in sys.path:
        sys.path.insert(0, parent)
    import cycles
    cycles.register()
    scene.render.engine = 'CYCLES'
    return "addon-registered"


try:
    how = ensure_cycles()
    print("M6T_ENGINE_OK", how)
except Exception as e:
    print("M6T_ENGINE_FAIL", repr(e))
    sys.exit(3)

scene = bpy.context.scene
scene.cycles.device = 'CPU'

# Thread control: Cycles-CPU is per-pixel deterministic (RNG seeded by
# pixel+sample), so a low fixed count on wasm still matches the many-threaded
# CI golden within threshold, while dodging the pthread-mem-growth wedge risk.
_threads = int(os.environ.get("M6_THREADS", "1"))
if _threads > 0:
    scene.render.threads_mode = 'FIXED'
    scene.render.threads = _threads

# Frame 1 (the framework renders `-f 1`; goldens are frame-1 output).
scene.frame_set(1)

scene.render.image_settings.file_format = 'PNG'
scene.render.filepath = base

print("M6T_RENDER_START engine=%s device=%s samples=%d res=%dx%d threads=%d adaptive=%s" % (
    scene.render.engine, scene.cycles.device, scene.cycles.samples,
    scene.render.resolution_x * scene.render.resolution_percentage // 100,
    scene.render.resolution_y * scene.render.resolution_percentage // 100,
    scene.render.threads, getattr(scene.cycles, "use_adaptive_sampling", "n/a")))
sys.stdout.flush()

# write_still saves render.filepath + ext verbatim (no frame padding) -> <base>.png
bpy.ops.render.render(write_still=True)
print("M6T_RENDER_DONE ->", scene.render.filepath + ".png")
sys.stdout.flush()
