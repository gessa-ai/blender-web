#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: CC0-1.0
#
# Render notes/m6-gpu-suite-real-scores.md from results.tsv (checkpoint after each test).
import sys
from collections import Counter, defaultdict

TSV = sys.argv[1]
rows = []
with open(TSV) as f:
    for ln in f:
        if ln.startswith("#") or not ln.strip():
            continue
        parts = ln.rstrip("\n").split("\t")
        while len(parts) < 10:
            parts.append("")
        rows.append(parts[:10])

by_engine = defaultdict(list)
for r in rows:
    by_engine[r[0]].append(r)

def aggregate(rs):
    c = Counter(r[3] for r in rs)
    return c

print("<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->")
print("<!-- SPDX-License-Identifier: CC0-1.0 -->")
print("# M6 GPU render suites (workbench + EEVEE) - REAL scores via the r35 render-result bridge")
print()
print("Measured with the TICK-PUMPED RENDER-RESULT BRIDGE (patch 0125): the BW_DIAG-gated")
print("hook in `WGPUTexture::read` kicks a tick-pumped async readback (AllowSpontaneous)")
print("whose true device bytes land in `/tmp/bw_readback_<seq>.bin`, decoded + oiiotool-")
print("compared to the staged goldens at Blender's own pinned thresholds. The bridge is")
print("PROVEN on the workbench factory cube (real shaded pixels, 0 GPU errors); see the")
print("self-test section. Each suite scene is booted as the STARTUP FILE (clean GPU context,")
print("no live open_mainfile).")
print()
print("This CORRECTS the r34-truth-pass premise that \"all 50 renders complete correctly and")
print("readback is the sole M6 blocker\": the readback path WORKS; the real blockers are")
print("render-side (see clusters).")
print()

total = Counter()
for eng in ("workbench", "eevee"):
    rs = by_engine.get(eng, [])
    if not rs:
        continue
    print("## %s (%d scored)" % (eng, len(rs)))
    print()
    print("| # | dir/test | verdict | mean_err | max_err | pct_over | gpuErr | cluster |")
    print("|---|----------|---------|----------|---------|----------|--------|---------|")
    for i, r in enumerate(rs, 1):
        eng_, dir_, test_, verdict, cluster, mean, maxe, pct, gerr, gsig = r
        total[verdict] += 1
        print("| %d | %s/%s | %s | %s | %s | %s | %s | %s |" % (
            i, dir_, test_, verdict, mean or "-", maxe or "-",
            (pct or "-").replace("|", "/"), gerr or "-", cluster or gsig or "-"))
    print()
    agg = aggregate(rs)
    print("**%s aggregate:** " % eng + ", ".join("%s=%d" % (k, v) for k, v in sorted(agg.items())))
    print()

print("## Aggregate (all scored)")
print()
print("| verdict | count |")
print("|---------|-------|")
for k, v in sorted(total.items()):
    print("| %s | %d |" % (k, v))
print()

# clusters
clusters = Counter(r[4] or r[9] or "unclustered" for r in rows if r[3] not in ("PASS",))
print("## Failure clusters")
print()
if not clusters:
    print("(none - all scored rows PASS)")
else:
    print("| cluster | count |")
    print("|---------|-------|")
    for k, v in clusters.most_common():
        print("| %s | %d |" % (k, v))
print()
print("### Cluster meanings")
print("- **render-bug:bindgroup-6v7** - workbench render draw: WebGPU BindGroup has 6 entries")
print("  but the layout expects 7 -> Invalid CommandBuffer -> Submit rejected -> black render.")
print("  A backend bind-completion defect (class of patch 0116), scene/feature dependent")
print("  (the factory default cube renders CLEAN, so it is not universal). REPORTED, not fixed.")
print("- **render-bug:gpu-validation / device-lost** - EEVEE-Next pipeline creation fails:")
print("  \"Storage texture WriteOnly used with Vertex/Fragment visibility -> Invalid")
print("  BindGroupLayout -> CreatePipeline\". EEVEE-Next binds write-only storage textures in")
print("  graphics stages, which WebGPU disallows (registered deferral: vertex-stage-rw-storage /")
print("  storage-texture-atomics). The render never runs, so there is no final texture to read -")
print("  NOT a readback blocker. REPORTED, not fixed.")
print("- **pixel-delta** - the render produced CLEAN pixels (0 GPU errors) that exceed the")
print("  golden threshold: a real shading/precision/feature delta, not a render crash.")
print("- **PASS** - real pixels within Blender's own pinned oiiotool tolerance.")
print()
print("### Colour-management caveat")
print("The decoder applies Blender's **Standard** view transform (linear->sRGB), verified on the")
print("oracle for the vast majority of scenes. The `colorspace/acescg_blackbody` and")
print("`colorspace/rec2020_lights` scenes use **ACES 2.0 / Rec.2020** display with a non-zero")
print("exposure, which the pure-python decoder does NOT replicate. Any pixel-delta on those two")
print("scenes is therefore CONFOUNDED by colour management and is not a pure render-accuracy")
print("number; they are measured for completeness but flagged here.")
