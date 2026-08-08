#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Build the COLD-at-boot function set (MANGLED names, for wasm-split --split-funcs)
# from paired llvm-nm listings of a name-bearing module:
#   nm_plain  = `llvm-nm --print-size <mod>`            (mangled names)
#   nm_demang = `llvm-nm --print-size --demangle <mod>` (demangled, same order)
# Classification reuses sandbox/m8-dce-ranking/classify.py subsystem regexes.
# A bucket is COLD iff it is not on the boot / first-pixels / first-interaction path.
import re, sys, collections

# Cold buckets = deferrable subsystems (RANKING.md items A,D,E,F,G,H,I + numpy).
# NOT included (hot or not cleanly separable here): CPython, OCIO, OIIO, freetype,
# openexr, tbb, zlib, png/jpeg, blender core (blenlib/bke/rna/draw/gpu/bmesh/wm/
# depsgraph/ed-other/modifiers), geonodes (needed at first-interaction), sculpt
# (no distinct namespace in classify.py -> folded into ed/bke, cannot cleanly cut).
COLD_BUCKETS = {
    "seq/VSE", "compositor", "grease_pencil",
    "ed:spreadsheet", "ed:clip/tracking", "ed:nla",
    "shaderc/glslang", "tint", "numpy",
}

RULES = [
    ("seq/VSE",            re.compile(r"blender::seq::|(^|[^A-Za-z])SEQ_|sequencer|::seq::")),
    ("compositor",         re.compile(r"blender::compositor::|blender::realtime_compositor|node_composite|(^|[^A-Za-z])COM_[A-Z]")),
    ("grease_pencil",      re.compile(r"grease_pencil|GreasePencil|gpencil|GPENCIL|bGPd|annotation")),
    ("geonodes(all)",      re.compile(r"blender::nodes::node_geo|node_geometry|GeometryNode|blender::geometry::")),
    ("ed:spreadsheet",     re.compile(r"spreadsheet")),
    ("ed:clip/tracking",   re.compile(r"space_clip|::clip_|tracking|libmv|(^|[^A-Za-z])mv::")),
    ("ed:nla",             re.compile(r"(^|[^A-Za-z])nla|NlaStrip|NlaTrack")),
    ("shaderc/glslang",    re.compile(r"glslang|shaderc|spvtools|(^|[^A-Za-z])spv::|SPIRV|HlslParse")),
    ("tint",               re.compile(r"(^|[^A-Za-z])tint::")),
    ("OpenColorIO",        re.compile(r"OpenColorIO|OCIO")),
    ("OpenImageIO",        re.compile(r"OpenImageIO|(^|[^A-Za-z])OIIO|pvt::")),
    ("numpy",              re.compile(r"npy_|PyArray|PyUFunc|numpy|_multiarray|multiarray|npymath|npysort")),
    ("CPython",            re.compile(r"(^|[^A-Za-z])_?Py[A-Z]|_Py_|PyInit")),
    ("freetype",           re.compile(r"(^|[^A-Za-z])(FT_|ft_|tt_|cff_|sfnt|af_|ps_|t1_|t42|pfr_|bdf_|pcf_|woff|gxv_|otv_|cid_|psaux|pshinter|psnames|autofit|smooth_|raster_|svg_)")),
    ("openexr/imath",      re.compile(r"(^|[^A-Za-z])(Imf|Imath|Iex|IlmThread)")),
    ("tbb",                re.compile(r"(^|[^A-Za-z])tbb::|tbb_|__TBB")),
]

def parse(path):
    line_re = re.compile(r"^([0-9a-fA-F]+)\s+([0-9a-fA-F]+)\s+([tTdD])\s+(.*)$")
    out = []
    with open(path, errors="replace") as f:
        for ln in f:
            m = line_re.match(ln)
            if not m: continue
            out.append((int(m.group(2), 16), m.group(3), m.group(4)))
    return out

def classify(demangled):
    for bname, rx in RULES:
        if rx.search(demangled):
            return bname
    return None

def main():
    nm_plain, nm_demang, out_file = sys.argv[1], sys.argv[2], sys.argv[3]
    plain = parse(nm_plain); demang = parse(nm_demang)
    if len(plain) != len(demang):
        sys.stderr.write(f"WARN: nm line count mismatch {len(plain)} vs {len(demang)}; pairing by index anyway\n")
    n = min(len(plain), len(demang))
    cold_names = []; by_bucket = collections.defaultdict(lambda: [0, 0])
    total_code = 0
    for i in range(n):
        size, typ, mangled = plain[i]
        _, typd, dem = demang[i]
        if typ not in "tT": continue
        total_code += size
        b = classify(dem)
        if b in COLD_BUCKETS:
            cold_names.append(mangled)
            by_bucket[b][0] += 1; by_bucket[b][1] += size
    with open(out_file, 'w') as f:
        f.write("\n".join(cold_names) + "\n")
    cold_bytes = sum(v[1] for v in by_bucket.values())
    cold_funcs = sum(v[0] for v in by_bucket.values())
    print(f"# total code bytes (t/T) = {total_code:,}")
    print(f"# COLD set: {cold_funcs:,} funcs, {cold_bytes:,} raw bytes "
          f"({cold_bytes/1048576:.2f} MiB, {100*cold_bytes/total_code:.2f}% of code)")
    print(f"{'cold bucket':22} {'funcs':>7} {'raw_bytes':>13} {'MiB':>7}")
    for b, (c, by) in sorted(by_bucket.items(), key=lambda kv: -kv[1][1]):
        print(f"{b:22} {c:>7} {by:>13,} {by/1048576:>7.2f}")
    print(f"# wrote {len(cold_names):,} mangled names -> {out_file}")

if __name__ == '__main__':
    main()
