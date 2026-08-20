# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later
#
# M6 Cycles suite — per-test wasm render driver (ONE BLEND PER node INVOCATION).
#
# Weans the Cycles-CPU render subset off cycles_render_tests.py, which spawns
# Blender subprocesses + multiprocessing (unavailable in single-process wasm
# python). The host runner (run_wasm_cycles.sh) drives one node invocation per
# test blend; this script registers the staged Cycles add-on before opening the
# blend, then renders frame 1 on Cycles-CPU with the blend's OWN scene settings
# (samples/resolution/seed are
# NOT overridden — parity requires the exact settings the committed golden was
# rendered with; the framework's get_arguments() likewise never overrides them).
#
# Invocation (from run_wasm_cycles.sh), with factory startup loaded first:
#   node blender.js --background --factory-startup --python render_test.py
#   env: M6_BLEND (blend opened after add-on registration),
#        M6_OUT_BASE (output path prefix; frame 1 -> <base>0001.png),
#        M6_CYCLES_ADDON_PARENT (staged cycles addon parent dir),
#        M6_THREADS (fixed CPU thread count; <=0 => auto).
import bpy
import os
import sys
from bpy.app.handlers import persistent

base = os.environ["M6_OUT_BASE"]
blend = os.path.abspath(os.environ["M6_BLEND"])


def register_cycles_before_load():
    # Source-tree boot (BLENDER_SYSTEM_RESOURCES=upstream) lacks
    # scripts/addons_core/cycles (copied only at install time), so the CYCLES
    # engine and, critically, its persistent version handler are unregistered
    # until we register the staged add-on. The _cycles C module is a builtin
    # (inittab, WITH_CYCLES), so import works.
    parent = os.environ.get("M6_CYCLES_ADDON_PARENT")
    if not parent:
        raise RuntimeError("M6_CYCLES_ADDON_PARENT is required")
    if parent not in sys.path:
        sys.path.insert(0, parent)
    import cycles
    from cycles import version_update

    handlers = bpy.app.handlers.version_update
    how = "addon-preregistered"
    if version_update.do_versions not in handlers:
        cycles.register()
        how = "addon-registered-before-load"
    if version_update.do_versions not in handlers:
        raise RuntimeError("Cycles version handler was not registered before blend load")
    return how


version_update_hits = []


@persistent
def record_version_update(_unused):
    version_update_hits.append(tuple(bpy.data.version))


try:
    how = register_cycles_before_load()
    print("M6T_ENGINE_OK", how)
    bpy.app.handlers.version_update.append(record_version_update)
    try:
        bpy.ops.wm.open_mainfile(filepath=blend)
    finally:
        if record_version_update in bpy.app.handlers.version_update:
            bpy.app.handlers.version_update.remove(record_version_update)

    file_version = tuple(bpy.data.version)
    if version_update_hits != [file_version]:
        raise RuntimeError(
            "version handler did not run exactly once after add-on registration: "
            f"hits={version_update_hits} loaded={file_version}"
        )
    if os.path.abspath(bpy.data.filepath) != blend:
        raise RuntimeError(f"loaded blend mismatch: {bpy.data.filepath!r} != {blend!r}")

    sampling_assertion = "NOT_APPLICABLE"
    if file_version <= (4, 2, 52):
        bad_scenes = [
            scene.name
            for scene in bpy.data.scenes
            if scene.cycles.sampling_pattern != "TABULATED_SOBOL"
        ]
        if bad_scenes:
            raise RuntimeError(
                "legacy Cycles sampling migration missing for scenes: " + ",".join(bad_scenes)
            )
        sampling_assertion = "TABULATED_SOBOL"
    print(
        "M6T_LEGACY_SETTINGS_OK",
        "file_version=" + ".".join(map(str, file_version)),
        "handler_hits=1",
        "addon_handler_preloaded=1",
        "sampling=" + sampling_assertion,
    )
except Exception as e:
    print("M6T_ENGINE_FAIL", repr(e))
    sys.exit(3)

scene = bpy.context.scene
scene.render.engine = 'CYCLES'
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
