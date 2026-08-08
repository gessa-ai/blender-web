# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later
#
# M6 GPU-suite (workbench/EEVEE) per-test render driver, ONE BLEND PER invocation.
# Sibling of wasm-first-render/render_test.py (Cycles) but engine-parameterized for
# the GPU engines. Loads the already-open positional blend, sets the engine from
# M6_ENGINE, renders frame 1 with the blend's OWN scene settings, writes PNG to
# M6_OUT_BASE + ".png". Tagged prints only; no golden re-authoring here.
import bpy, os, sys

base = os.environ["M6_OUT_BASE"]
engine = os.environ.get("M6_ENGINE", "BLENDER_WORKBENCH")

scene = bpy.context.scene
try:
    scene.render.engine = engine
    print("M6G_ENGINE_OK", engine)
except Exception as e:
    print("M6G_ENGINE_FAIL", repr(e)); sys.exit(3)

scene.frame_set(1)
scene.render.image_settings.file_format = 'PNG'
scene.render.filepath = base

print("M6G_RENDER_START engine=%s res=%dx%d" % (
    scene.render.engine,
    scene.render.resolution_x * scene.render.resolution_percentage // 100,
    scene.render.resolution_y * scene.render.resolution_percentage // 100))
sys.stdout.flush()
try:
    bpy.ops.render.render(write_still=True)
    print("M6G_RENDER_DONE ->", scene.render.filepath + ".png")
except Exception as e:
    print("M6G_RENDER_FAIL", repr(e)); sys.exit(4)
sys.stdout.flush()
