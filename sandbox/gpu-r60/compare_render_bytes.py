#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-3.0-or-later

import json
import math
import struct
import sys


def read_web(path):
    data = open(path, "rb").read()
    if data[:4] != b"BWRB":
        raise ValueError("not a BWRB capture")
    _, width, height, fmt, texel, row_bytes, data_bytes = struct.unpack_from("<7I", data, 4)
    if fmt != 40 or texel != 8:
        raise ValueError(f"expected RGBA16Float fmt=40/texel=8, got {fmt}/{texel}")
    payload = memoryview(data)[32:32 + data_bytes]
    rows = []
    for y in range(height):
        row = []
        base = y * row_bytes
        for x in range(width):
            row.append(struct.unpack_from("<4e", payload, base + x * texel))
        rows.append(row)
    return width, height, rows


def read_native(path, width, height):
    values = struct.unpack(f"<{width * height * 4}f", open(path, "rb").read())
    return [[values[(y * width + x) * 4:(y * width + x + 1) * 4]
             for x in range(width)] for y in range(height)]


def metrics(web, native, flip_web):
    errors = []
    for y, web_row in enumerate(web):
        wy = len(web) - 1 - y if flip_web else y
        for x in range(len(web_row)):
            for channel in range(3):
                errors.append(abs(float(web[wy][x][channel]) - float(native[y][x][channel])))
    return {
        "flip_web": flip_web,
        "mean_abs": sum(errors) / len(errors),
        "rms": math.sqrt(sum(error * error for error in errors) / len(errors)),
        "max_abs": max(errors),
        "over_0_016": sum(error > 0.016 for error in errors),
        "sample_count": len(errors),
    }


width, height, web = read_web(sys.argv[1])
native = read_native(sys.argv[2], width, height)
results = [metrics(web, native, False), metrics(web, native, True)]
result = min(results, key=lambda item: item["mean_abs"])
result["width"] = width
result["height"] = height
result["alternatives"] = results
print(json.dumps(result, indent=2))
