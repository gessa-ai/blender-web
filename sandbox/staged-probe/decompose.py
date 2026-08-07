#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: CC0-1.0
"""Decompose the file_packager .data manifest into ranked size tables.

Input: sandbox/staged-probe/manifest_raw.txt (lines like
  {filename:"/bw/...",start:N,end:M})
Output: ranked per-top-level-dir and per-python-package tables.
"""
import re, sys, collections

RE = re.compile(r'\{filename:"([^"]*)",start:(\d+),end:(\d+)\}')

entries = []
total = 0
with open(sys.argv[1]) as f:
    for line in f:
        for fn, s, e in RE.findall(line):
            sz = int(e) - int(s)
            entries.append((fn, sz))
            total += sz

print(f"# files: {len(entries)}   total bytes: {total:,} ({total/1048576:.1f} MiB)\n")

def mib(b): return f"{b/1048576:7.2f}"

# --- Top-level under /bw ---
top = collections.Counter()
topn = collections.Counter()
for fn, sz in entries:
    parts = fn.strip("/").split("/")
    # /bw/<a>/<b>/...
    key = "/".join(parts[:2]) if len(parts) >= 2 else parts[0]
    top[key] += sz
    topn[key] += 1
print("== Top-level (/bw/<a>/<b>) ==")
for k, v in top.most_common():
    print(f"{mib(v)} MiB  {v:>11,}  {topn[k]:>5} files  {k}")

# --- Python stdlib: group by first dir under python3.13 ---
print("\n== python3.13 subtree (by first component under lib/python3.13) ==")
py = collections.Counter(); pyn = collections.Counter()
PYROOT = "python/lib/python3.13"
for fn, sz in entries:
    f = fn.strip("/")
    if PYROOT in f:
        rest = f.split(PYROOT+"/",1)[1] if PYROOT+"/" in f else ""
        comp = rest.split("/")[0] if rest else "(root .py files)"
        # if it's a top-level module file vs package dir
        py[comp] += sz; pyn[comp] += 1
for k, v in py.most_common(40):
    print(f"{mib(v)} MiB  {v:>11,}  {pyn[k]:>5}  {k}")

# --- scripts subtree ---
print("\n== scripts subtree (by first two components under scripts/) ==")
sc = collections.Counter(); scn = collections.Counter()
for fn, sz in entries:
    f = fn.strip("/")
    if f.startswith("bw/scripts/"):
        rest = f.split("bw/scripts/",1)[1]
        comp = "/".join(rest.split("/")[:2])
        sc[comp]+=sz; scn[comp]+=1
for k,v in sc.most_common(30):
    print(f"{mib(v)} MiB  {v:>11,}  {scn[k]:>5}  {k}")

# --- datafiles subtree ---
print("\n== datafiles subtree (by first component under datafiles/) ==")
df = collections.Counter(); dfn = collections.Counter()
for fn, sz in entries:
    f = fn.strip("/")
    if f.startswith("bw/datafiles/"):
        rest = f.split("bw/datafiles/",1)[1]
        comp = rest.split("/")[0]
        df[comp]+=sz; dfn[comp]+=1
for k,v in df.most_common(40):
    print(f"{mib(v)} MiB  {v:>11,}  {dfn[k]:>5}  {k}")

# --- lib.zip / site-packages if any ---
print("\n== other python subtrees (site-packages, lib-dynload, wheels) ==")
misc = collections.Counter()
for fn, sz in entries:
    f = fn.strip("/")
    for tag in ("site-packages","lib-dynload",".whl","wheels","__pycache__"):
        if tag in f:
            misc[tag]+=sz
for k,v in misc.most_common():
    print(f"{mib(v)} MiB  {v:>11,}  {k}")
