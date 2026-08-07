# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later
#
# M6 first-wasm-render — minimal deterministic Cycles-CPU render of the
# factory-startup default cube. Run identically on the wasm node binary and the
# native pin oracle; the two PNGs are idiff'd with Blender's own 0.016/1
# thresholds. No test-runner script (cycles_render_tests.py spawns subprocesses
# + multiprocessing, which the wasm single-process python lacks) — direct bpy so
# both sides execute byte-identical settings.
import bpy, os, sys

out = os.environ.get("M6_OUT", "/tmp")
samples = int(os.environ.get("M6_SAMPLES", "16"))
res = int(os.environ.get("M6_RES", "64"))

scene = bpy.context.scene


def ensure_cycles():
    # Native oracle: CYCLES already registered -> first assignment succeeds.
    # wasm node build: the cycles addon is not in the source addons_core tree,
    # so register it by hand from a staged copy (M6_CYCLES_ADDON_PARENT). The
    # _cycles C module is a builtin (inittab, WITH_CYCLES) so import works.
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
    print("M6_ENGINE_OK", how)
except Exception as e:
    print("M6_ENGINE_FAIL", repr(e))
    sys.exit(3)

scene.cycles.device = 'CPU'
scene.cycles.samples = samples

# Thread control. Cycles-CPU is deterministic per-pixel regardless of thread
# count (RNG seeded by pixel+sample), so a low count on wasm still matches the
# many-threaded native oracle within threshold. M6_THREADS<=0 -> auto/all.
_threads = int(os.environ.get("M6_THREADS", "0"))
if _threads > 0:
    scene.render.threads_mode = 'FIXED'
    scene.render.threads = _threads
scene.cycles.use_adaptive_sampling = False
try:
    scene.cycles.use_denoising = False
except Exception:
    pass
scene.cycles.seed = 0
scene.render.resolution_x = res
scene.render.resolution_y = res
scene.render.resolution_percentage = 100
scene.render.image_settings.file_format = 'PNG'
scene.render.image_settings.color_mode = 'RGBA'
scene.render.filepath = os.path.join(out, "cube_")

print("M6_RENDER_START engine=%s device=%s samples=%d res=%dx%d threads=%s" % (
    scene.render.engine, scene.cycles.device, scene.cycles.samples,
    scene.render.resolution_x, scene.render.resolution_y, scene.render.threads))
sys.stdout.flush()
bpy.ops.render.render(write_still=True)
print("M6_RENDER_DONE ->", scene.render.frame_path(frame=1))
sys.stdout.flush()
