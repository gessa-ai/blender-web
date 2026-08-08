#!/usr/bin/env python3
# SPDX-License-Identifier: CC0-1.0
# Post-DCE per-subsystem attribution of the SHIPPED opt wasm, from
# `llvm-nm --print-size --demangle` output (functions only, type t/T).
import re, sys, collections

path = sys.argv[1]
# ordered (bucket, regex) rules; FIRST match wins -> specific before general.
RULES = [
    # ---- DCE candidates (task) ----
    ("seq/VSE",            re.compile(r"blender::seq::|(^|[^A-Za-z])SEQ_|sequencer|::seq::")),
    ("compositor",         re.compile(r"blender::compositor::|blender::realtime_compositor|node_composite|(^|[^A-Za-z])COM_[A-Z]")),
    ("grease_pencil",      re.compile(r"grease_pencil|GreasePencil|gpencil|GPENCIL|bGPd|annotation")),
    ("geonodes(all)",      re.compile(r"blender::nodes::node_geo|node_geometry|GeometryNode|blender::geometry::")),
    ("ed:spreadsheet",     re.compile(r"spreadsheet")),
    ("ed:clip/tracking",   re.compile(r"space_clip|::clip_|tracking|libmv|(^|[^A-Za-z])mv::")),
    ("ed:nla",             re.compile(r"(^|[^A-Za-z])nla|NlaStrip|NlaTrack")),
    # ---- shader toolchain (split candidate, not compile-out) ----
    ("shaderc/glslang",    re.compile(r"glslang|shaderc|spvtools|(^|[^A-Za-z])spv::|SPIRV|HlslParse")),
    ("tint",               re.compile(r"(^|[^A-Za-z])tint::")),
    # ---- deps (context; mostly not cut candidates) ----
    ("OpenColorIO",        re.compile(r"OpenColorIO|OCIO")),
    ("OpenImageIO",        re.compile(r"OpenImageIO|(^|[^A-Za-z])OIIO|pvt::")),
    ("numpy",              re.compile(r"npy_|PyArray|PyUFunc|numpy|_multiarray|multiarray|npymath|npysort")),
    ("CPython",            re.compile(r"(^|[^A-Za-z])_?Py[A-Z]|_Py_|PyInit|(^|[^A-Za-z])(sre_|unicode_|bytes_|bytearray_|float_|long_|list_|dict_|tuple_|set_|frame_|gen_|code_|type_|object_|builtin_|abstract_|complex_|slice_|range_|enum_|iter_|method_|module_|import_|marshal|pickle|_pickle|_io_|_ssl|_socket|posix_|os_|time_|math_|cmath_|itertools|functools|collections|_json|_csv|_struct|_random|_sha|_md5|_blake|_hashlib|zlibmodule|binascii|_datetime|_decimal|_ctypes|_elementtree|expat_|pyexpat|faulthandler|_thread|_asyncio|_bisect|_heapq|_lsprof|_opcode|_operator|_queue|_statistics|_contextvars|_weakref|_locale|_codecs|audioop|termios|select_|fcntl_|resource_|syslog_|grp_|pwd_|readline)")),
    ("freetype",           re.compile(r"(^|[^A-Za-z])(FT_|ft_|tt_|cff_|sfnt|af_|ps_|t1_|t42|pfr_|bdf_|pcf_|woff|gxv_|otv_|cid_|psaux|pshinter|psnames|autofit|smooth_|raster_|svg_)")),
    ("openexr/imath",      re.compile(r"(^|[^A-Za-z])(Imf|Imath|Iex|IlmThread)")),
    ("tbb",                re.compile(r"(^|[^A-Za-z])tbb::|tbb_|__TBB")),
    ("zlib/zstd/deflate",  re.compile(r"(^|[^A-Za-z])(deflate|inflate|ZSTD_|ZDICT|zng_|adler32|crc32|gz|libdeflate)")),
    ("png/jpeg/tiff/jph",  re.compile(r"(^|[^A-Za-z])(png_|jpeg_|jinit|jpeg|TIFF|_TIFF|LZW|opj_|openjph|ojph|jpg_)")),
    # ---- Blender core & the rest ----
    ("blender::nodes(other)", re.compile(r"blender::nodes::|node_shader|node_function|NodeDeclaration")),
    ("blender::draw",      re.compile(r"blender::draw::|(^|[^A-Za-z])DRW_|(^|[^A-Za-z])drw_")),
    ("blender::gpu",       re.compile(r"blender::gpu::|(^|[^A-Za-z])GPU_|(^|[^A-Za-z])gpu_")),
    ("blender::bke",       re.compile(r"blender::bke::|(^|[^A-Za-z])BKE_")),
    ("blender::ed(other)", re.compile(r"blender::ed::|(^|[^A-Za-z])ED_")),
    ("blender::bmesh",     re.compile(r"(^|[^A-Za-z])BM_|(^|[^A-Za-z])bmesh|blender::bmesh")),
    ("blender::rna",       re.compile(r"(^|[^A-Za-z])RNA_|rna_|(^|[^A-Za-z])pyrna|_bpy")),
    ("blender::blenlib",   re.compile(r"(^|[^A-Za-z])BLI_|blender::(?!nodes|seq|compositor|draw|gpu|bke|ed|bmesh|geometry)")),
    ("blender::depsgraph", re.compile(r"(^|[^A-Za-z])DEG_|blender::deg")),
    ("blender::wm",        re.compile(r"(^|[^A-Za-z])WM_|(^|[^A-Za-z])wm_")),
    ("blender::modifiers", re.compile(r"(^|[^A-Za-z])MOD_|modifier")),
]
FALLBACK = "unclassified(libc/c++/glue)"

buckets = collections.defaultdict(lambda: [0,0])  # name -> [count, bytes]
line_re = re.compile(r"^([0-9a-fA-F]+)\s+([0-9a-fA-F]+)\s+([tTdD])\s+(.*)$")
total_code = 0; total_data = 0
with open(path, errors="replace") as f:
    for ln in f:
        m = line_re.match(ln)
        if not m: continue
        size = int(m.group(2),16); typ = m.group(3); name = m.group(4)
        if typ in "dD":
            total_data += size; continue
        total_code += size
        for bname, rx in RULES:
            if rx.search(name):
                buckets[bname][0]+=1; buckets[bname][1]+=size; break
        else:
            buckets[FALLBACK][0]+=1; buckets[FALLBACK][1]+=size

rows = sorted(buckets.items(), key=lambda kv: -kv[1][1])
print(f"# TOTAL code(t/T) bytes = {total_code:,}   data(d/D) bytes = {total_data:,}")
print(f"{'bucket':28} {'count':>7} {'raw_bytes':>13} {'MiB':>7} {'%code':>6}")
for name,(c,b) in rows:
    print(f"{name:28} {c:>7} {b:>13,} {b/1048576:>7.2f} {100*b/total_code:>6.2f}")
