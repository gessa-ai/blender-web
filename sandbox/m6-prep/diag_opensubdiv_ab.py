# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later
#
# M6 Cycles suite — OpenSubdiv attribution A/B (diagnostic, run on the NATIVE oracle).
#
# The wasm build is WITH_OPENSUBDIV=OFF, so Subsurf/Multires modifiers are silently
# disabled at render ("Disabled, built without OpenSubdiv"). This renders each Cycles
# test blend on the native pin oracle with those modifiers ALSO disabled — mimicking
# the wasm build's geometry. Diffing an oracle-subdiv-disabled render against the wasm
# render (from run_wasm_cycles.sh) with each test's threshold isolates OpenSubdiv as a
# cause: MATCH => the ONLY delta is subdivision (wasm engine otherwise faithful, would
# pass with WITH_OPENSUBDIV=ON); DIFFER => an additional residual delta remains.
#
# Usage (produces oracle-subdiv-disabled PNGs into OUTDIR; diff externally with oiiotool):
#   ROOT=$(git rev-parse --show-toplevel) OUTDIR=/tmp/nosubdiv \
#   oracle/blender-5.2.0/Blender.app/Contents/MacOS/Blender --background \
#     --factory-startup --python sandbox/m6-prep/diag_opensubdiv_ab.py
# Then per test: oiiotool <OUTDIR>/<dir>_<test>.png <wasm.png> --fail <thr> --failpercent <fp> --diff
# The committed result of this A/B is results-wasm-cycles-attribution.tsv.
import bpy
import os
import sys

root = os.environ["ROOT"]
outdir = os.environ["OUTDIR"]
os.makedirs(outdir, exist_ok=True)

blends = []
with open(os.path.join(root, "sandbox/m6-prep/manifest.tsv")) as f:
    for line in f:
        if line.startswith("#") or not line.strip():
            continue
        c = line.rstrip("\n").split("\t")
        if c[0] == "cycles":
            blends.append((c[1], c[2], os.path.join(root, c[3])))

for d, t, path in blends:
    bpy.ops.wm.open_mainfile(filepath=path)
    s = bpy.context.scene
    disabled = 0
    for o in bpy.data.objects:
        for m in list(getattr(o, "modifiers", [])):
            if m.type in ("SUBSURF", "MULTIRES"):
                m.show_render = False
                m.show_viewport = False
                disabled += 1
    s.render.engine = 'CYCLES'
    s.cycles.device = 'CPU'
    s.frame_set(1)
    s.render.image_settings.file_format = 'PNG'
    s.render.filepath = os.path.join(outdir, "%s_%s" % (d, t))
    bpy.ops.render.render(write_still=True)
    print("NOSUBDIV_DONE %s/%s disabled=%d" % (d, t, disabled))
    sys.stdout.flush()
