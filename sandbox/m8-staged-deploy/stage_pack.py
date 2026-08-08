#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-3.0-or-later
#
# stage_pack.py - repackage a monolithic emscripten --preload-file payload into a
# staged pair, entirely in the DEPLOY bundle (never touches the build tree).
#
# Input  (read-only): a built blender_browser.{js,data} (monolith preload).
# Output (bundle):    blender_browser.js  (glue with the baked manifest rewritten
#                         to STAGE-0 real files + zero-length placeholders for every
#                         deferred file, so the preload creates the FULL directory
#                         tree - post-boot mkdir is impossible under the 0555 /bw
#                         mount, but writing files into existing dirs works),
#                     blender_browser.data (= stage-0 bytes only; the baked preload
#                         fetches THIS, so boot blocks on stage-0 alone),
#                     stage1.data + stage1-manifest.json (deferred bytes, streamed
#                         in post-first-pixels by stage1-loader.js via FS.writeFile).
#
# The .data format is a bare byte concatenation; each manifest entry is a
# [start,end) slice. We re-slice the monolith into two concatenations and rewrite
# the offsets. No emscripten relink; the glue is edited as a bundle artifact.
#
# Classification (oracle-validated in notes/m8-staged-loading.md sections 2-3):
#   DROP  - never needed at runtime: __pycache__/.pyc (already pruned upstream),
#           pip .whl.  Omitted from both stages.
#   DEFER - not touched at English --factory-startup boot (-> stage-1):
#           dead stdlib modules, non-enabled addons (rigify, ...), CJK/intl fonts
#           (keep Inter + DejaVuSansMono), non-default colormanagement LUTs
#           (keep config.ocio + the default AgX display path).  [--defer-datafiles]
#   KEEP  - everything else (-> stage-0).
import argparse
import json
import os
import re
import sys

RE_ENTRY = re.compile(r'\{filename:"((?:[^"\\]|\\.)*)",start:(\d+),end:(\d+)\}')

# --- oracle-validated partition sets (notes/m8-staged-loading.md sec 2-3) --------
DEAD_STDLIB = (
    "idlelib/", "tkinter/", "turtledemo/", "turtle.py", "ensurepip/", "pydoc_data/",
    "lib2to3/", "venv/", "/test/", "distutils/", "antigravity.py", "this.py",
    "__phello__", "zoneinfo/", "wsgiref/", "xmlrpc/", "asyncio/", "concurrent/",
    "curses/", "unittest/", "sqlite3/", "dbm/", "pydoc.py", "doctest.py", "pdb.py",
    "profile.py", "cProfile.py", "smtplib.py", "ftplib.py", "poplib.py", "imaplib.py",
    "mailbox.py", "cgitb.py",
)
# Addons whose register() runs at --factory-startup (native oracle) MUST be stage-0.
STAGE0_ADDONS = (
    "bl_pkg", "io_scene_fbx", "io_scene_gltf2", "io_anim_bvh", "pose_library",
    "io_curve_svg", "io_mesh_uv_layout",
)
INTL_FONT_KEEP = ("Inter.woff2", "DejaVuSansMono.woff2")
CM_LUT_KEEP = ("config.ocio", "AgX_Base_sRGB.cube", "Guard_Rail_Shaper_EOTF.spi1d",
               "AgX_False_Color.spi1d")


def in_py(fn):
    return "/bw/python/lib/python3.13" in fn


def classify(fn, defer_datafiles):
    """Return 'drop' | 'defer' | 'keep'."""
    # DROP: never needed at runtime.
    if "__pycache__" in fn or fn.endswith(".pyc"):
        return "drop"
    if fn.endswith(".whl"):
        return "drop"
    # DEFER: python stdlib not imported at boot.
    if in_py(fn) and any(d in fn for d in DEAD_STDLIB):
        return "defer"
    # DEFER: addons not enabled at --factory-startup.
    if "/bw/scripts/addons_core/" in fn and not any(
        "addons_core/" + a + "/" in fn for a in STAGE0_ADDONS
    ):
        return "defer"
    if defer_datafiles:
        # DEFER: non-Latin / CJK fonts (English UI never demands them at boot).
        if "/datafiles/fonts/" in fn and not any(k in fn for k in INTL_FONT_KEEP):
            return "defer"
        # DEFER: colormanagement display LUTs except the default AgX-sRGB path.
        if "/datafiles/colormanagement/" in fn and (fn.endswith(".cube") or fn.endswith(".spi1d")) \
           and not any(k in fn for k in CM_LUT_KEEP):
            return "defer"
    return "keep"


def parse_manifest(glue_text):
    i = glue_text.find("loadPackage({files:[")
    if i < 0:
        sys.exit("stage_pack: FATAL: loadPackage({files:[ not found in glue")
    # Find the enclosing loadPackage({ ... }) argument object.
    open_brace = glue_text.find("{", i + len("loadPackage("))
    # remote_package_size marks the tail of the metadata object.
    m = re.search(r"\],remote_package_size:(\d+)\}\)", glue_text[i:])
    if not m:
        sys.exit("stage_pack: FATAL: remote_package_size tail not found")
    meta_start = open_brace
    meta_end = i + m.end()  # position just past the closing '})'
    meta_text = glue_text[meta_start:meta_end]
    entries = [(fn, int(s), int(e)) for fn, s, e in RE_ENTRY.findall(meta_text)]
    remote_size = int(m.group(1))
    return meta_start, meta_end, entries, remote_size


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bin", required=True, help="dir with monolith blender_browser.{js,data}")
    ap.add_argument("--out", required=True, help="bundle bin/ output dir")
    ap.add_argument("--defer-datafiles", dest="defer_datafiles", action="store_true", default=True)
    ap.add_argument("--no-defer-datafiles", dest="defer_datafiles", action="store_false")
    ap.add_argument("--dry-run", action="store_true", help="print stats only")
    args = ap.parse_args()

    glue_path = os.path.join(args.bin, "blender_browser.js")
    data_path = os.path.join(args.bin, "blender_browser.data")
    glue = open(glue_path).read()
    meta_start, meta_end, entries, remote_size = parse_manifest(glue)
    blob = open(data_path, "rb").read()
    if remote_size != len(blob):
        print(f"stage_pack: WARN remote_package_size {remote_size} != data bytes {len(blob)}",
              file=sys.stderr)

    buckets = {"keep": [], "defer": [], "drop": []}
    for fn, s, e in entries:
        buckets[classify(fn, args.defer_datafiles)].append((fn, s, e))

    def total(b):
        return sum(e - s for _, s, e in buckets[b])

    print(f"entries={len(entries)}  data={len(blob):,} bytes")
    for b in ("keep", "defer", "drop"):
        n = len(buckets[b]); t = total(b)
        print(f"  {b:5s}: {n:5d} files  {t:12,d} bytes  ({t/1048576:7.2f} MiB)")
    stage0_bytes = total("keep")
    print(f"  => stage0.data {stage0_bytes/1048576:.2f} MiB   stage1.data {total('defer')/1048576:.2f} MiB")

    if args.dry_run:
        # show the largest DEFER contributors for a sanity check
        big = sorted(buckets["defer"], key=lambda x: x[2] - x[1], reverse=True)[:12]
        print("  top DEFER files:")
        for fn, s, e in big:
            print(f"    {(e-s):10,d}  {fn}")
        return

    os.makedirs(args.out, exist_ok=True)

    # --- build stage0.data + new KEEP offsets, and stage1.data + stage1 manifest ---
    stage0 = bytearray()
    stage1 = bytearray()
    new_entries = []          # for the rewritten baked manifest (stage-0 + placeholders)
    stage1_manifest = []      # for stage1-loader.js
    for fn, s, e in entries:
        b = classify(fn, args.defer_datafiles)
        if b == "keep":
            start = len(stage0)
            stage0 += blob[s:e]
            new_entries.append((fn, start, len(stage0)))
        elif b == "defer":
            start = len(stage1)
            stage1 += blob[s:e]
            stage1_manifest.append({"filename": fn, "start": start, "end": len(stage1)})
            # zero-length placeholder in stage-0 so the DIRECTORY TREE is created at
            # preload (post-boot mkdir is impossible); real bytes arrive via
            # FS.writeFile from stage1-loader.js.
            new_entries.append((fn, 0, 0))
        # drop: omit entirely

    # rewrite the baked metadata object in the glue
    files_js = ",".join(
        '{filename:"%s",start:%d,end:%d}' % (fn, s, e) for fn, s, e in new_entries
    )
    new_meta = "{files:[" + files_js + "],remote_package_size:%d}" % len(stage0)
    # glue[meta_start:meta_end] spanned the object '{...}' PLUS loadPackage's ')'.
    # new_meta is the complete replacement object; re-add ONLY the ')'.
    new_glue = glue[:meta_start] + new_meta + ")" + glue[meta_end:]

    with open(os.path.join(args.out, "blender_browser.js"), "w") as f:
        f.write(new_glue)
    with open(os.path.join(args.out, "blender_browser.data"), "wb") as f:
        f.write(stage0)
    with open(os.path.join(args.out, "stage1.data"), "wb") as f:
        f.write(stage1)
    with open(os.path.join(args.out, "stage1-manifest.json"), "w") as f:
        json.dump({"total_bytes": len(stage1), "files": stage1_manifest}, f)

    print(f"stage_pack: wrote stage-0 glue+data ({len(stage0):,} B), "
          f"stage1.data ({len(stage1):,} B, {len(stage1_manifest)} files), manifest")


if __name__ == "__main__":
    main()
