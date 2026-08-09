#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: CC0-1.0

"""Render the final Phase A M6 GPU rescore note from results.tsv."""

import sys
from collections import Counter, defaultdict


tsv = sys.argv[1]
rows = []
with open(tsv) as handle:
    for line in handle:
        if line.startswith("#") or not line.strip():
            continue
        parts = line.rstrip("\n").split("\t")
        parts += [""] * (10 - len(parts))
        rows.append(parts[:10])

by_engine = defaultdict(list)
for row in rows:
    by_engine[row[0]].append(row)


def emit_table(engine):
    engine_rows = by_engine[engine]
    print("## %s (%d rows)" % (engine.capitalize(), len(engine_rows)))
    print()
    print("| # | Scene | Verdict | Mean error | Max error | Pixels over | GPU errors | Cluster |")
    print("|---|---|---|---:|---:|---:|---:|---|")
    for index, row in enumerate(engine_rows, 1):
        _, directory, test, verdict, cluster, mean, maximum, percent, gpu_errors, signature = row
        print("| %d | `%s/%s` | %s | %s | %s | %s | %s | %s |" % (
            index,
            directory,
            test,
            verdict,
            mean or "-",
            maximum or "-",
            (percent or "-").replace("|", "/"),
            gpu_errors or "0",
            cluster or signature or "-",
        ))
    print()
    counts = Counter(row[3] for row in engine_rows)
    print("**Aggregate:** " + ", ".join("%s=%d" % item for item in sorted(counts.items())))
    print()


print("<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->")
print("<!-- SPDX-License-Identifier: CC0-1.0 -->")
print("# M6 GPU render suites: final Phase A rescore")
print()
print("This is the clean 50-scene browser rescore at outer HEAD `ac03fa6e540136f539c8cf84994a8e623b6f28ec`.")
print("Each blend booted as the startup file in a fresh headed Chromium context. The run used no")
print("persisted captures and no `REUSE=1`; every scored row has a fresh manifest. Workbench")
print("pixels came from patch 0125's tick-pumped device-byte bridge and were compared to the")
print("pinned Blender goldens at 0.016 / 1 percent. EEVEE uses 4/255 / 0.08 percent, but this")
print("run produced no EEVEE bridge pixels, so no EEVEE row receives a pixel PASS or FAIL.")
print()
print("Completeness: exactly 20 Workbench plus 30 EEVEE rows, zero duplicates, zero missing/LFS")
print("inputs, zero RIG-FAIL, zero browser crash, and zero reused manifests. The native census")
print("also holds at 149 PASS / 7 FAIL / 2 CRASH, with static shaders 956/973.")
print()
print("## Headline")
print()
print("- Workbench improves to **12 PASS / 8 FAIL**, with no load flakes or render crashes.")
print("- EEVEE is **28 NO-CAPTURE / 2 RENDER-ERR**. All 30 rows have zero readback kicks and")
print("  zero device-byte captures. Therefore Phase A's required non-black behavioral acceptance")
print("  is not met, including `principled_bsdf_default`.")
print("- Phase A did remove the old C1-C4 validation flood: no fresh manifest contains the old")
print("  Vertex-visible writable-storage, WriteOnly-format, or per-stage-limit signatures.")
print("- The measured EEVEE residue is: 20 rows return `OK BLENDER_EEVEE` with zero GPU errors")
print("  but do not fire the readback diagnostic hook inside `WGPUTexture::read`: layer-view")
print("  wrappers have no local `texture_` and return early. Seven rows first fail on RG11B10Ufloat ReadWrite;")
print("  `principled_bsdf_transmission` instead hits a writable RGBA16Float storage alias between")
print("  bindings 2 and 3 at mip 7; and sheen plus subsurface never emit a START marker within")
print("  the bounded 200-second render-progress window.")
print("- All four shadow rows stop first at the Phase A' RG11B10Ufloat ReadWrite BGL failure.")
print("  This matrix does not reach and therefore does not measure the Phase B atomic path.")
print()

emit_table("workbench")
emit_table("eevee")

print("## Workbench residuals")
print()
print("The two DoF scenes each emit 96 validation errors from three distinct root classes before")
print("their invalid-command-buffer cascades:")
print()
print("1. Depth32FloatStencil8 offers UnfilterableFloat or Depth where the layout expects Float.")
print("2. An RGBA16Float attachment view exposes mipLevelCount 3, while attachments require 1.")
print("3. RG8Unorm is sampled and writable as a render attachment in the same synchronization scope.")
print()
print("The remaining clean Workbench pixel deltas are `aa-disabled`, `aa-single-pass`, `in_front`,")
print("and `x-ray_1`. The `acescg_blackbody` and `rec2020_lights` rows remain intentionally")
print("reported but color-management-confounded: the bridge decoder applies Standard sRGB, while")
print("those scenes use ACES 2.0 / Rec.2020 with exposure. Under D-10 they are not evidence of a")
print("backend pixel regression and cannot be accepted as faithful M6 parity until the real display")
print("transform or caller-facing readback path is used.")
print()
print("## EEVEE outcome taxonomy")
print()
print("- `NO-CAPTURE / no-capture`: render returns OK with zero captured validation errors, but")
print("  the readback diagnostic hook inside `WGPUTexture::read` does not fire because layer-view")
print("  wrappers have no local `texture_` and return early, so no final device bytes were captured.")
print("- `NO-CAPTURE / render-blocked:gpu-validation`: the render returns, but a measured validation")
print("  blocker prevents a capturable final result. Seven are RG11B10Ufloat ReadWrite; one is the separate")
print("  RGBA16Float writable-storage alias in `principled_bsdf_transmission`.")
print("- `RENDER-ERR / render-start-timeout`: the bounded retry observes no fd2 START marker within")
print("  200 seconds, so there is no proof the bpy timer entered `_bw_render`. The second bounded")
print("  run confirms no START or terminal marker in that window, not an in-render loop hang.")
print()
print("## Evidence")
print()
print("- Raw matrix: `sandbox/gpu-r35/results.tsv`")
print("- Per-scene manifests and decoded Workbench images: `sandbox/gpu-r35/caps/`")
print("- fd2 control: `sandbox/gpu-m6-rescore-final/marker-control/`")
print("- Native census: `sandbox/gpu-m6-rescore-final/native-census-summary.txt`")
print("- Proof images and contact sheet: `sandbox/gpu-m6-rescore-final/proof/`")
