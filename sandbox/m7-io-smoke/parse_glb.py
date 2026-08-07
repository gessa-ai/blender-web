#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later
#
# GLB (binary glTF) structural validator/comparator — stdlib only (no new deps).
# Usage:
#   parse_glb.py <file.glb>              -> print a structural summary
#   parse_glb.py <a.glb> <b.glb>         -> semantic compare (mesh/accessor parity)
# Parity contract (per M7 brief): magic/chunks parse; mesh + accessor counts match.
import sys, json, struct

_COMPONENT = {5120: "BYTE", 5121: "UBYTE", 5122: "SHORT", 5123: "USHORT",
              5125: "UINT", 5126: "FLOAT"}


def parse(path):
    with open(path, "rb") as f:
        blob = f.read()
    magic, version, length = struct.unpack_from("<4sII", blob, 0)
    assert magic == b"glTF", "bad GLB magic %r" % magic
    chunks, off = [], 12
    while off < length:
        clen, ctype = struct.unpack_from("<I4s", blob, off)
        cdata = blob[off + 8: off + 8 + clen]
        chunks.append((ctype.decode("ascii", "replace").strip("\x00"), clen, cdata))
        off += 8 + clen
    gltf = json.loads(next(c[2] for c in chunks if c[0] == "JSON"))
    bin_size = next((c[1] for c in chunks if c[0].startswith("BIN")), 0)
    return blob, magic, version, length, chunks, gltf, bin_size


def summary(path):
    blob, magic, version, length, chunks, gltf, bin_size = parse(path)
    acc = gltf.get("accessors", [])
    meshes = gltf.get("meshes", [])
    prim_total = sum(len(m.get("primitives", [])) for m in meshes)
    print("GLB", path)
    print("  magic=%s version=%d total_len=%d file_bytes=%d"
          % (magic.decode(), version, length, len(blob)))
    print("  chunks=%s" % [(t, l) for t, l, _ in chunks])
    print("  bin_chunk_bytes=%d" % bin_size)
    print("  generator=%r" % gltf.get("asset", {}).get("generator"))
    print("  gltf_version=%r" % gltf.get("asset", {}).get("version"))
    print("  counts: scenes=%d nodes=%d meshes=%d primitives=%d accessors=%d "
          "bufferViews=%d buffers=%d materials=%d"
          % (len(gltf.get("scenes", [])), len(gltf.get("nodes", [])),
             len(meshes), prim_total, len(acc),
             len(gltf.get("bufferViews", [])), len(gltf.get("buffers", [])),
             len(gltf.get("materials", []))))
    for i, a in enumerate(acc):
        print("  accessor[%d] type=%s comp=%s count=%d"
              % (i, a.get("type"), _COMPONENT.get(a.get("componentType"),
                 a.get("componentType")), a.get("count")))
    for mi, m in enumerate(meshes):
        for pi, p in enumerate(m.get("primitives", [])):
            print("  mesh[%d].prim[%d] attrs=%s indices=%s mode=%s"
                  % (mi, pi, sorted(p.get("attributes", {})),
                     p.get("indices"), p.get("mode", 4)))
    total_buf = sum(b.get("byteLength", 0) for b in gltf.get("buffers", []))
    print("  total_buffer_byteLength=%d" % total_buf)
    return gltf, bin_size


def _digest(gltf, bin_size):
    """Structural fingerprint that must match across builds (ignores generator
    string / byte-layout ordering, compares the semantic mesh contract)."""
    acc = sorted((a.get("type"), a.get("componentType"), a.get("count"))
                 for a in gltf.get("accessors", []))
    prims = sorted((tuple(sorted(p.get("attributes", {}))), p.get("mode", 4))
                   for m in gltf.get("meshes", []) for p in m.get("primitives", []))
    return {
        "meshes": len(gltf.get("meshes", [])),
        "primitives": sum(len(m.get("primitives", [])) for m in gltf.get("meshes", [])),
        "accessors": acc,
        "prim_attrs": prims,
        "nodes": len(gltf.get("nodes", [])),
        "materials": len(gltf.get("materials", [])),
        "total_buffer_byteLength": sum(b.get("byteLength", 0)
                                       for b in gltf.get("buffers", [])),
        "bin_chunk_bytes": bin_size,
    }


def compare(a_path, b_path):
    ga, ba = parse(a_path)[5], parse(a_path)[6]
    gb, bb = parse(b_path)[5], parse(b_path)[6]
    da, db = _digest(ga, ba), _digest(gb, bb)
    ok = da == db
    print("GLB_COMPARE %s vs %s -> %s" % (a_path, b_path, "PASS" if ok else "FAIL"))
    if not ok:
        for k in da:
            if da[k] != db[k]:
                print("  DIFF %s: %r != %r" % (k, da[k], db[k]))
    return ok


if __name__ == "__main__":
    if len(sys.argv) == 2:
        summary(sys.argv[1])
    elif len(sys.argv) == 3:
        sys.exit(0 if compare(sys.argv[1], sys.argv[2]) else 1)
    else:
        print(__doc__)
        sys.exit(2)
