#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: CC0-1.0
"""Extract a real STAGE-0 .data (sliced concat of the S6 stage-0 file set) from
the monolith blender_browser.data, for on-wire throttle measurement. The .data
format is a bare byte-concatenation, so this IS what file_packager would emit."""
import re, os
DATA="build-wasm-windowed-opt/bin/blender_browser.data"
MAN ="sandbox/staged-probe/manifest_raw.txt"
OUT ="sandbox/staged-probe/web/stage0.data"
RE=re.compile(r'\{filename:"([^"]*)",start:(\d+),end:(\d+)\}')
ents=[]
for line in open(MAN):
    for fn,s,e in RE.findall(line): ents.append((fn,int(s),int(e)))
blob=open(DATA,"rb").read()

# multiprocessing REMOVED: native oracle confirms it IS imported at factory-startup boot.
DEAD_STDLIB=("idlelib/","tkinter/","turtledemo/","turtle.py","ensurepip/","pydoc_data/",
 "lib2to3/","venv/","/test/","distutils/","antigravity.py","this.py","__phello__",
 "zoneinfo/","wsgiref/","xmlrpc/","asyncio/","concurrent/","curses/",
 "unittest/","sqlite3/","dbm/","pydoc.py","doctest.py","pdb.py","profile.py","cProfile.py",
 "smtplib.py","ftplib.py","poplib.py","imaplib.py","mailbox.py","cgitb.py")
# Addons ENABLED at --factory-startup (native oracle: register() runs at boot) MUST be
# stage-0. cycles is WITH_CYCLES=OFF -> not in payload. Deferrable = rigify (big),
# node_wrangler, viewport_vr_preview, ui_translate, hydra_storm.
STAGE0_ADDONS=("bl_pkg","io_scene_fbx","io_scene_gltf2","io_anim_bvh","pose_library",
 "io_curve_svg","io_mesh_uv_layout")
INTL_FONT_KEEP=("Inter.woff2","DejaVuSansMono.woff2")
CM_LUT_KEEP=("config.ocio","AgX_Base_sRGB.cube","Guard_Rail_Shaper_EOTF.spi1d","AgX_False_Color.spi1d")
def inpy(fn): return "/bw/python/lib/python3.13" in fn
def s6(fn):
    if "__pycache__" in fn or fn.endswith(".pyc"): return False
    if inpy(fn) and any(d in fn for d in DEAD_STDLIB): return False
    if "/bw/scripts/addons_core/" in fn and not any("addons_core/"+a+"/" in fn for a in STAGE0_ADDONS): return False
    if "/datafiles/fonts/" in fn and not any(k in fn for k in INTL_FONT_KEEP): return False
    if "/datafiles/colormanagement/" in fn and (fn.endswith(".cube") or fn.endswith(".spi1d")) \
       and not any(k in fn for k in CM_LUT_KEEP): return False
    if fn.endswith(".whl"): return False
    return True

s0=bytearray(); s1=bytearray(); n0=n1=0
for fn,s,e in ents:
    if s6(fn): s0+=blob[s:e]; n0+=1
    else:      s1+=blob[s:e]; n1+=1
open(OUT,"wb").write(s0)
open("sandbox/staged-probe/web/stage1.data","wb").write(s1)
print(f"stage0.data: {n0} files, {len(s0):,} bytes ({len(s0)/1048576:.2f} MiB)")
print(f"stage1.data: {n1} files, {len(s1):,} bytes ({len(s1)/1048576:.2f} MiB)")
