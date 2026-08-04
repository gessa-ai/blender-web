#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
#
# M1.12 dump comparison tool. Structural diff of two state_dump.py outputs,
# reporting the first N divergences as JSON paths. Because state_dump.py emits
# only quantized integers, strings, bools and sha256 hashes (no floats), the
# baseline comparison is exact equality -- the tolerance IS the 1e-6 micro-unit
# quantization baked into the dump. An optional integer --tolerance loosens
# numeric-leaf comparisons by that many micro-units for divergence triage;
# hashes and structural counts still require exact match under tolerance
# (see caveat below), so keep it 0 for the parity gate.
#
# Usage:
#   compare_dumps.py <golden.json> <other.json> [--tolerance N] [--max N]
#   compare_dumps.py --selftest <golden.json>
#
# Exit code: 0 = identical (PASS), 1 = divergences (FAIL), 2 = usage error.
#
# Ported for the web from (new file, no upstream original) @ fbe6228777e7

import copy
import json
import sys

# Keys whose integer leaves are structural (counts / indices / handles), never
# measurements -- --tolerance must NOT loosen these, or it would mask real
# divergences (e.g. a mesh gaining a vertex). Everything else that is an int is
# treated as a quantized measurement eligible for tolerance.
STRUCTURAL_INT_KEYS = {
    "count", "vertex_count", "edge_count", "loop_count", "polygon_count",
    "node_count", "link_count", "fcurve_count", "keyframe_count", "bone_count",
    "spline_count", "point_count", "slot_count", "layer_count", "users",
    "line_count", "channels", "depth", "array_index", "order_u",
    "resolution_u", "resolution_x", "resolution_y", "resolution_percentage",
    "fps", "frame_start", "frame_end", "frame_current", "schema_version",
    "quant_scale",
}


def _is_hash(s):
    return isinstance(s, str) and len(s) == 64 and all(
        c in "0123456789abcdef" for c in s)


def diff(a, b, path, out, tol, max_div, last_key=None):
    if len(out) >= max_div:
        return
    if type(a) is not type(b) and not (
            isinstance(a, (int, float)) and isinstance(b, (int, float))
            and not isinstance(a, bool) and not isinstance(b, bool)):
        out.append((path, "type", a, b))
        return
    if isinstance(a, dict):
        for k in sorted(set(a) | set(b)):
            child = "%s.%s" % (path, k) if path else k
            if k not in a:
                out.append((child, "only_in_B", None, _brief(b[k])))
            elif k not in b:
                out.append((child, "only_in_A", _brief(a[k]), None))
            else:
                diff(a[k], b[k], child, out, tol, max_div, last_key=k)
            if len(out) >= max_div:
                return
    elif isinstance(a, list):
        if len(a) != len(b):
            out.append((path + ".__len__", "list_len", len(a), len(b)))
        for i in range(min(len(a), len(b))):
            diff(a[i], b[i], "%s[%d]" % (path, i), out, tol, max_div,
                 last_key=last_key)
            if len(out) >= max_div:
                return
    else:
        if isinstance(a, bool) or isinstance(b, bool):
            if a != b:
                out.append((path, "value", a, b))
        elif isinstance(a, int) and isinstance(b, int):
            if a != b:
                if tol > 0 and last_key not in STRUCTURAL_INT_KEYS \
                        and abs(a - b) <= tol:
                    pass  # within micro-unit tolerance
                else:
                    out.append((path, "value", a, b))
        else:
            if a != b:
                kind = "hash" if (_is_hash(a) or _is_hash(b)) else "value"
                out.append((path, kind, a, b))


def _brief(v):
    """Compact representation of a subtree for 'only in one side' reports."""
    if isinstance(v, dict):
        return "{%s}" % ",".join(sorted(v)[:6])
    if isinstance(v, list):
        return "[len=%d]" % len(v)
    return v


def compare(golden, other, tolerance=0, max_div=50):
    out = []
    diff(golden, other, "", out, tolerance, max_div)
    return out


def print_report(divs, golden_name, other_name):
    if not divs:
        print("PASS  %s == %s  (0 divergences)" % (golden_name, other_name))
        return
    print("FAIL  %s vs %s  (%d divergence%s%s)" % (
        golden_name, other_name, len(divs),
        "" if len(divs) == 1 else "s",
        ", showing first 50" if len(divs) >= 50 else ""))
    for path, kind, a, b in divs:
        print("  [%s] %s" % (kind, path or "<root>"))
        print("      A: %s" % _fmt(a))
        print("      B: %s" % _fmt(b))


def _fmt(v):
    s = json.dumps(v)
    return s if len(s) <= 100 else s[:97] + "..."


def selftest(golden_path):
    golden = json.load(open(golden_path))
    print("SELFTEST golden=%s" % golden_path)

    # 1) golden vs itself -> PASS
    d0 = compare(golden, copy.deepcopy(golden))
    print_report(d0, "golden", "golden(copy)")
    ok1 = (len(d0) == 0)

    # 2) golden vs a mutated copy -> FAIL with readable diff
    mutated = copy.deepcopy(golden)
    mutations = _mutate(mutated)
    d1 = compare(golden, mutated)
    print("--- injected mutations: %s" % ", ".join(mutations))
    print_report(d1, "golden", "mutated")
    ok2 = (len(d1) >= len(mutations))

    verdict = "SELFTEST_PASS" if (ok1 and ok2) else "SELFTEST_FAIL"
    print(verdict)
    return 0 if (ok1 and ok2) else 1


def _mutate(dump):
    """Inject a few detectable changes; return human labels for each."""
    labels = []
    colls = dump["collections"]
    # Mutate a mesh vertex_count + position hash if any mesh exists.
    meshes = colls.get("meshes", {}).get("items", {})
    if meshes:
        name = sorted(meshes)[0]
        meshes[name]["vertex_count"] += 1
        labels.append("meshes.%s.vertex_count +1" % name)
        if "position_hash" in meshes[name]:
            meshes[name]["position_hash"] = "0" * 64
            labels.append("meshes.%s.position_hash zeroed" % name)
    # Drop an object to exercise 'only_in_A'.
    objs = colls.get("objects", {}).get("items", {})
    if objs:
        victim = sorted(objs)[0]
        del objs[victim]
        colls["objects"]["count"] -= 1
        labels.append("objects.%s removed" % victim)
    if not labels:  # fallback for a minimal dump
        dump["schema_version"] = 999
        labels.append("schema_version -> 999")
    return labels


def main():
    argv = sys.argv[1:]
    if not argv:
        print(__doc__)
        sys.exit(2)
    if argv[0] == "--selftest":
        if len(argv) < 2:
            print("usage: compare_dumps.py --selftest <golden.json>")
            sys.exit(2)
        sys.exit(selftest(argv[1]))

    tol = 0
    max_div = 50
    positional = []
    i = 0
    while i < len(argv):
        if argv[i] == "--tolerance":
            tol = int(argv[i + 1]); i += 2
        elif argv[i] == "--max":
            max_div = int(argv[i + 1]); i += 2
        else:
            positional.append(argv[i]); i += 1
    if len(positional) != 2:
        print("usage: compare_dumps.py <golden.json> <other.json> "
              "[--tolerance N] [--max N]")
        sys.exit(2)
    golden = json.load(open(positional[0]))
    other = json.load(open(positional[1]))
    divs = compare(golden, other, tolerance=tol, max_div=max_div)
    print_report(divs, positional[0], positional[1])
    sys.exit(0 if not divs else 1)


if __name__ == "__main__":
    main()
