#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: CC0-1.0
"""Measure staged-loading partitions by slicing the real blender_browser.data.

The .data is a bare concatenation of file bytes (offsets live in the .js manifest),
so a stage's real file_packager .data == the concatenation of its files' bytes.
We slice those exact bytes out of the monolith; brotli -q11 only the headline
subsets (raw for the rest — raw is the tree-shake story). Pinned to the measured
binary, immune to lib/wasm churn.
"""
import re, sys, brotli, time

DATA = "build-wasm-windowed-opt/bin/blender_browser.data"
MAN  = "sandbox/staged-probe/manifest_raw.txt"
RE = re.compile(r'\{filename:"([^"]*)",start:(\d+),end:(\d+)\}')
BROTLI = set(sys.argv[1:])  # names to brotli-q11; others report raw only

entries = []
with open(MAN) as f:
    for line in f:
        for fn, s, e in RE.findall(line):
            entries.append((fn, int(s), int(e)))
blob = open(DATA, "rb").read()

DEAD_STDLIB = ("idlelib/", "tkinter/", "turtledemo/", "turtle.py",
               "ensurepip/", "pydoc_data/", "lib2to3/", "venv/",
               "/test/", "distutils/", "antigravity.py", "this.py",
               "__phello__", "zoneinfo/", "wsgiref/", "xmlrpc/",
               "asyncio/", "multiprocessing/", "concurrent/", "curses/",
               "unittest/", "sqlite3/", "dbm/",
               "pydoc.py", "doctest.py", "pdb.py", "profile.py", "cProfile.py",
               "smtplib.py", "ftplib.py", "poplib.py", "imaplib.py",
               "mailbox.py", "cgitb.py")
STAGE0_ADDONS = ("addons_core/bl_pkg/",)
INTL_FONT_KEEP = ("Inter.woff2", "DejaVuSansMono.woff2")
CM_LUT_KEEP = ("config.ocio", "AgX_Base_sRGB.cube", "Guard_Rail_Shaper_EOTF.spi1d",
               "AgX_False_Color.spi1d")

def is_pycache(fn):  return "__pycache__" in fn or fn.endswith(".pyc")
def is_py(fn):       return fn.endswith(".py")
def opt_level(fn):
    if ".opt-1.pyc" in fn: return 1
    if ".opt-2.pyc" in fn: return 2
    if fn.endswith(".pyc"): return 0
    return None
def in_python(fn):   return "/bw/python/lib/python3.13" in fn
def is_dead_stdlib(fn): return in_python(fn) and any(d in fn for d in DEAD_STDLIB)
def is_addon(fn):    return "/bw/scripts/addons_core/" in fn
def is_stage0_addon(fn): return any(a in fn for a in STAGE0_ADDONS)
def is_font(fn):     return "/datafiles/fonts/" in fn
def is_cm(fn):       return "/datafiles/colormanagement/" in fn
def is_cm_lut(fn):   return is_cm(fn) and (fn.endswith(".cube") or fn.endswith(".spi1d"))
def is_wheel(fn):    return fn.endswith(".whl")

def measure(name, pred, do_brotli):
    n = 0; parts = []
    for fn, s, e in entries:
        if pred(fn):
            parts.append(blob[s:e]); n += 1
    raw = sum(len(p) for p in parts)
    if do_brotli and parts:
        t = time.time()
        br = len(brotli.compress(b"".join(parts), quality=11))
        bs = f" br {br/1048576:6.2f} MiB ({time.time()-t:.0f}s)"
    else:
        bs = ""
    print(f"{name:46s} {n:5d}f  raw {raw/1048576:7.2f} MiB{bs}", flush=True)

# stage-0 cumulative
def s1(fn):  return not is_pycache(fn)                                   # drop pyc, keep .py
def s2(fn):  return s1(fn) and not is_dead_stdlib(fn)                    # + dead stdlib
def s3(fn):
    if is_addon(fn) and not is_stage0_addon(fn): return False            # + non-boot addons
    return s2(fn)
def s4(fn):
    if is_font(fn) and not any(k in fn for k in INTL_FONT_KEEP): return False  # + intl fonts
    return s3(fn)
def s5(fn):
    if is_cm_lut(fn) and not any(k in fn for k in CM_LUT_KEEP): return False   # + CM LUTs
    return s4(fn)
def s6(fn):
    if is_wheel(fn): return False                                        # + pip wheel
    return s5(fn)

print("== python code strategy comparison (whole python subtree) ==")
measure("python .py sources only", lambda fn: in_python(fn) and is_py(fn), "pyonly" in BROTLI)
measure("python pyc all 3 opt levels", lambda fn: in_python(fn) and opt_level(fn) is not None, False)
measure("python pyc opt-0 only", lambda fn: in_python(fn) and opt_level(fn)==0, "pyc0" in BROTLI)

print("\n== cumulative STAGE-0 (data only) ==")
measure("S1 drop __pycache__ (keep .py)", s1, "s1" in BROTLI)
measure("S2  + defer dead stdlib", s2, False)
measure("S3  + defer non-boot addons_core", s3, False)
measure("S4  + defer intl/CJK fonts", s4, False)
measure("S5  + defer CM display LUTs", s5, False)
measure("S6  + drop pip wheel  == STAGE-0", s6, "s6" in BROTLI)

print("\n== STAGE-1 remainder ==")
measure("STAGE-1 (all not in S6)", lambda fn: not s6(fn), "stage1" in BROTLI)
print("\nDONE", flush=True)
