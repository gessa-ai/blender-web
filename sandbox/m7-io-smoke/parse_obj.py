#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later
#
# Wavefront-OBJ structural validator/comparator — stdlib only.
# Usage:
#   parse_obj.py <file.obj>            -> summary (v/vn/vt/f/o counts)
#   parse_obj.py <a.obj> <b.obj>       -> compare element counts
import sys


def parse(path):
    c = {"v": 0, "vn": 0, "vt": 0, "f": 0, "o": 0, "g": 0, "s": 0, "usemtl": 0}
    faces_deg = []  # vertices-per-face, to check topology
    with open(path, "r", errors="replace") as fh:
        for line in fh:
            tok = line.split()
            if not tok:
                continue
            k = tok[0]
            if k in c:
                c[k] += 1
            if k == "f":
                faces_deg.append(len(tok) - 1)
    c["_face_degrees"] = sorted(set(faces_deg))
    c["_total_face_corners"] = sum(faces_deg)
    return c


def summary(path):
    c = parse(path)
    print("OBJ", path)
    print("  v=%d vt=%d vn=%d f=%d o=%d g=%d usemtl=%d"
          % (c["v"], c["vt"], c["vn"], c["f"], c["o"], c["g"], c["usemtl"]))
    print("  face_degrees=%s total_face_corners=%d"
          % (c["_face_degrees"], c["_total_face_corners"]))
    return c


def compare(a, b):
    ca, cb = parse(a), parse(b)
    keys = ["v", "vt", "vn", "f", "o", "_face_degrees", "_total_face_corners"]
    ok = all(ca[k] == cb[k] for k in keys)
    print("OBJ_COMPARE %s vs %s -> %s" % (a, b, "PASS" if ok else "FAIL"))
    if not ok:
        for k in keys:
            if ca[k] != cb[k]:
                print("  DIFF %s: %r != %r" % (k, ca[k], cb[k]))
    return ok


if __name__ == "__main__":
    if len(sys.argv) == 2:
        summary(sys.argv[1])
    elif len(sys.argv) == 3:
        sys.exit(0 if compare(sys.argv[1], sys.argv[2]) else 1)
    else:
        print(__doc__)
        sys.exit(2)
