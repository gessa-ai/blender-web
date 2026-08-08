#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-3.0-or-later
#
# M6 r35: pick the render-result dump from a bridge_render capture dir, decode it, and
# compare to the staged golden with oiiotool at the pinned per-engine thresholds
# (exit-code = verdict, exactly the m6-prep oracle comparator invocation).
#
# The render-result read is identified as the LAST (highest-seq) capture whose w/h match
# the render resolution and whose wgpu_format is a colour format (workbench emits exactly
# one; EEVEE may read intermediate passes, so "last full-res colour read" = combined).
#
# Usage: score.py <capdir> <golden> <thr> <fp> [--colorspace linear|direct] [--json out]

import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
COLOR_FMTS = (22, 23, 27, 28, 40, 41)  # RGBA8/BGRA8/(s)rgb + RGBA16F/RGBA32F


def pick_render_result(caps, resw, resh):
    cands = [c for c in caps if c.get("fmt") in COLOR_FMTS
             and c.get("w") == resw and c.get("hgt") == resh]
    if not cands:
        # fall back: any colour cap at all (largest area, then highest seq)
        cands = [c for c in caps if c.get("fmt") in COLOR_FMTS]
    if not cands:
        return None
    cands.sort(key=lambda c: c.get("seq", 0))
    return cands[-1]


def run(cmd):
    p = subprocess.run(cmd, capture_output=True, text=True)
    return p.returncode, p.stdout + p.stderr


def main():
    a = sys.argv[1:]
    capdir, golden, thr, fp = a[0], a[1], a[2], a[3]
    colorspace = "linear"
    jsonout = None
    i = 4
    while i < len(a):
        if a[i] == "--colorspace":
            colorspace = a[i + 1]; i += 2
        elif a[i] == "--json":
            jsonout = a[i + 1]; i += 2
        else:
            i += 1

    man = json.load(open(os.path.join(capdir, "manifest.json")))
    resw, resh = man.get("res", [128, 128])
    sentinel = man.get("sentinel")
    caps = man.get("caps", [])
    gpuerrs = man.get("gpuErrorSample", [])
    gpu_sig = error_signature(gpuerrs)

    result = {"capdir": capdir, "golden": golden, "sentinel": sentinel,
              "ncaps": len(caps), "gpuErrorCount": man.get("gpuErrorCount", 0),
              "gpu_sig": gpu_sig}

    if man.get("pageCrashed") and not caps:
        result["verdict"] = "RENDER-CRASH"
        result["cluster"] = ("render-crash:" + gpu_sig) if gpu_sig else "render-crash"
        result["note"] = "tab crashed/device-lost during render; gpuErrors=%d" % man.get("gpuErrorCount", 0)
        emit(result, jsonout); return

    if not sentinel or not str(sentinel).startswith("OK"):
        result["verdict"] = "RENDER-ERR"
        result["cluster"] = "render-exception"
        result["note"] = str(sentinel)
        emit(result, jsonout); return

    rr = pick_render_result(caps, resw, resh)
    if rr is None:
        result["verdict"] = "NO-CAPTURE"
        # No WGPUTexture::read fired at all: the render never produced a final texture. With
        # GPU errors present this is a render-BLOCKED scene (e.g. EEVEE-Next pipeline creation
        # fails on the storage-texture visibility deferral), not a readback miss.
        if man.get("gpuErrorCount", 0) > 0:
            result["cluster"] = ("render-blocked:" + gpu_sig) if gpu_sig else "render-blocked"
        else:
            result["cluster"] = "no-capture"
        result["note"] = "no colour render-result dump; gpuErrors=%d; caps=%s" % (
            man.get("gpuErrorCount", 0),
            [(c.get("w"), c.get("hgt"), c.get("fmt")) for c in caps])
        emit(result, jsonout); return

    result["render_result"] = {"seq": rr["seq"], "w": rr["w"], "h": rr["hgt"], "fmt": rr["fmt"]}
    binpath = os.path.join(capdir, rr["file"])
    decoded = os.path.join(capdir, "render_result.png")
    rc, out = run(["python3", os.path.join(HERE, "decode_readback.py"), binpath, decoded,
                   "--colorspace", colorspace, "--flip", "vertical", "--channels", "3", "--info"])
    if rc != 0 or not os.path.exists(decoded):
        result["verdict"] = "DECODE-ERR"
        result["cluster"] = "decode-error"
        result["note"] = out.strip()[-300:]
        emit(result, jsonout); return
    result["decode"] = out.strip().split("  ", 2)[-1]
    # A rendered-black result with GPU errors = a real render bug (draw rejected), not a
    # pixel-parity failure. Classify it as such so the table separates render bugs from
    # precision/feature deltas (per the measure mandate: report render bugs, do not fix).
    nzfrac = 0.0
    try:
        nzfrac = float(result["decode"].split("nzFrac=")[1].split()[0])
    except Exception:
        pass
    if nzfrac == 0.0:
        result["verdict"] = "RENDER-BLACK"
        result["cluster"] = ("render-bug:" + gpu_sig) if gpu_sig else "render-black"
        result["note"] = "render-result all-zero; gpuErrors=%d" % man.get("gpuErrorCount", 0)
        emit(result, jsonout); return

    # Force the golden to 3-channel RGB so oiiotool --diff channel counts match (these
    # scenes are film_transparent=False, alpha uniformly 1; RGB carries all signal).
    golden3 = os.path.join(capdir, "golden_rgb.png")
    run(["oiiotool", golden, "--ch", "R,G,B", "-o", golden3])

    rc, out = run(["oiiotool", golden3, decoded, "--fail", str(thr), "--failpercent", str(fp), "--diff"])
    # parse metrics
    mean = maxe = pctover = None
    for ln in out.splitlines():
        s = ln.strip()
        if s.startswith("Mean error"):
            mean = s.split("=")[-1].strip() if "=" in s else s
        if "Max error" in s:
            # e.g. "  Max error  = 0.51 @ (..)"
            try:
                maxe = s.split("Max error")[1].split("=")[1].strip().split()[0]
            except Exception:
                maxe = None
        if "over" in s and "%" in s:
            pctover = s
    result["oiiotool_rc"] = rc
    result["mean_error"] = mean
    result["max_error"] = maxe
    result["pct_over"] = pctover.strip() if pctover else None
    result["verdict"] = "PASS" if rc == 0 else "FAIL"
    if rc == 0:
        result["cluster"] = "pixel-pass"
    elif man.get("gpuErrorCount", 0) > 0:
        # non-black but the draw threw GPU errors: a corrupted render, not a clean
        # precision/feature delta. Cluster it as a render bug so the table stays honest.
        result["cluster"] = ("render-bug:" + gpu_sig) if gpu_sig else "render-corrupt"
    else:
        result["cluster"] = "pixel-delta"
    emit(result, jsonout)


def error_signature(lines):
    """Collapse the GPU error sample into a short cluster signature."""
    for l in lines:
        if "did not match the expected number of entries" in l:
            import re
            m = re.search(r"entries \((\d+)\).*expected number of entries \((\d+)\)", l)
            if m:
                return "bindgroup-%sv%s" % (m.group(1), m.group(2))
            return "bindgroup-count"
        if "GPU-LOST" in l or "device" in l.lower() and "lost" in l.lower():
            return "device-lost"
    for l in lines:
        if "GPUValidationError" in l:
            return "gpu-validation"
    return ""


def emit(result, jsonout):
    if jsonout:
        json.dump(result, open(jsonout, "w"), indent=2)
    print(json.dumps(result))


if __name__ == "__main__":
    main()
