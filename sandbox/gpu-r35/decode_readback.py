#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-3.0-or-later
#
# M6 r35 render-result bridge: decode a diagnostic-readback dump
# (/tmp/bw_readback_<seq>.bin, written by WGPUTexture::diag_kick_readback via the
# BW_DIAG-gated hook in WGPUTexture::read) into an 8-bit PNG for oiiotool comparison
# against the staged M6 goldens.
#
# Dump format (see wgpu_texture.cc diag_complete): an 8-word LE header
#   {"BWRB", ver, w, h, wgpu_format, texel_bytes, row_bytes(tight), data_bytes}
# followed by h rows of row_bytes (the 256-byte copy padding already stripped).
#
# The GPU combined-result texture is scene-LINEAR; the Standard view transform these
# render tests use is exactly the sRGB OETF with a [0,1] clamp (display_device=sRGB,
# view_transform=Standard, look=None, exposure=0, gamma=1 -- verified on the oracle).
# So --colorspace linear replicates Blender's save-time colour management for those
# scenes.  --colorspace direct is for already-display textures (BGRA8/*Srgb).
#
# No numpy / PIL dependency (host lacks both): pure struct + zlib PNG encoder.
#
# Usage:
#   decode_readback.py <in.bin> <out.png> [--colorspace linear|direct]
#                       [--flip none|vertical] [--channels 3|4] [--info]

import struct
import sys
import zlib

FMT = {
    7: ("R16Uint", 2, 1, "uint16"),
    21: ("RG16Float", 4, 2, "half"),
    22: ("RGBA8Unorm", 4, 4, "unorm8"),
    23: ("RGBA8UnormSrgb", 4, 4, "unorm8"),
    27: ("BGRA8Unorm", 4, 4, "unorm8"),
    28: ("BGRA8UnormSrgb", 4, 4, "unorm8"),
    40: ("RGBA16Float", 8, 4, "half"),
    41: ("RGBA32Float", 16, 4, "float"),
    48: ("Depth32Float", 4, 1, "float"),
}
BGRA_FORMATS = (27, 28)
SRGB_FORMATS = (23, 28)  # values are already display-encoded


def parse(path):
    with open(path, "rb") as f:
        raw = f.read()
    if len(raw) < 32 or raw[0:4] != b"BWRB":
        raise ValueError("not a BWRB dump: %s" % path)
    _, ver, w, h, fmt, texel, row_bytes, data_bytes = struct.unpack_from("<4sIIIIIII", raw, 0)
    body = raw[32:]
    return dict(ver=ver, w=w, h=h, fmt=fmt, texel=texel, row_bytes=row_bytes,
                data_bytes=data_bytes, body=body)


def decode_floats(hdr):
    """Return a flat list of per-texel [r,g,b,a] floats (linear/native, row-major top-down)."""
    w, h, fmt, texel = hdr["w"], hdr["h"], hdr["fmt"], hdr["texel"]
    body = hdr["body"]
    row_bytes = hdr["row_bytes"]
    if fmt not in FMT:
        raise ValueError("unsupported wgpu_format=%d" % fmt)
    _, texel_expect, nch, kind = FMT[fmt]
    px = []
    for y in range(h):
        off = y * row_bytes
        for x in range(w):
            p = off + x * texel
            if kind == "unorm8":
                b0, b1, b2, b3 = body[p], body[p + 1], body[p + 2], body[p + 3]
                r, g, b, a = b0 / 255.0, b1 / 255.0, b2 / 255.0, b3 / 255.0
                if fmt in BGRA_FORMATS:
                    r, b = b, r
            elif kind == "half":
                comps = struct.unpack_from("<%de" % nch, body, p)
                r = comps[0]
                g = comps[1] if nch > 1 else 0.0
                b = comps[2] if nch > 2 else 0.0
                a = comps[3] if nch > 3 else 1.0
            elif kind == "float":
                comps = struct.unpack_from("<%df" % nch, body, p)
                r = comps[0]
                g = comps[1] if nch > 1 else r
                b = comps[2] if nch > 2 else r
                a = comps[3] if nch > 3 else 1.0
            elif kind == "uint16":
                v = struct.unpack_from("<H", body, p)[0] / 65535.0
                r = g = b = v
                a = 1.0
            else:
                r = g = b = 0.0
                a = 1.0
            px.append((r, g, b, a))
    return px


def lin_to_srgb(c):
    if c <= 0.0:
        return 0.0
    if c >= 1.0:
        c = 1.0
    if c <= 0.0031308:
        return c * 12.92
    return 1.055 * (c ** (1.0 / 2.4)) - 0.055


def to_u8(px, colorspace, channels):
    out = bytearray()
    if colorspace == "linear":
        conv = lambda c: int(round(lin_to_srgb(c) * 255.0))
    else:  # direct: values are already display-referred [0,1]
        conv = lambda c: int(round(min(max(c, 0.0), 1.0) * 255.0))
    aconv = lambda c: int(round(min(max(c, 0.0), 1.0) * 255.0))  # alpha never view-transformed
    for (r, g, b, a) in px:
        out.append(conv(r)); out.append(conv(g)); out.append(conv(b))
        if channels == 4:
            out.append(aconv(a))
    return bytes(out)


def write_png(path, w, h, rgb, channels):
    def chunk(tag, data):
        return (struct.pack(">I", len(data)) + tag + data +
                struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))
    color_type = 6 if channels == 4 else 2  # 6=RGBA, 2=RGB
    ihdr = struct.pack(">IIBBBBB", w, h, 8, color_type, 0, 0, 0)
    stride = w * channels
    raw = bytearray()
    for y in range(h):
        raw.append(0)  # filter type 0 (None)
        raw += rgb[y * stride:(y + 1) * stride]
    idat = zlib.compress(bytes(raw), 9)
    with open(path, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n")
        f.write(chunk(b"IHDR", ihdr))
        f.write(chunk(b"IDAT", idat))
        f.write(chunk(b"IEND", b""))


def stats(px):
    n = len(px)
    if n == 0:
        return "empty"
    mins = [min(p[i] for p in px) for i in range(3)]
    maxs = [max(p[i] for p in px) for i in range(3)]
    nz = sum(1 for p in px if p[0] or p[1] or p[2])
    return "nzFrac=%.4f min=(%.3f,%.3f,%.3f) max=(%.3f,%.3f,%.3f)" % (
        nz / n, mins[0], mins[1], mins[2], maxs[0], maxs[1], maxs[2])


def main():
    a = sys.argv[1:]
    if len(a) < 2:
        print("usage: decode_readback.py <in.bin> <out.png> "
              "[--colorspace linear|direct] [--flip none|vertical] [--channels 3|4] [--info]")
        sys.exit(2)
    inp, outp = a[0], a[1]
    colorspace = "linear"
    flip = "vertical"
    channels = 3
    info = False
    i = 2
    while i < len(a):
        if a[i] == "--colorspace":
            colorspace = a[i + 1]; i += 2
        elif a[i] == "--flip":
            flip = a[i + 1]; i += 2
        elif a[i] == "--channels":
            channels = int(a[i + 1]); i += 2
        elif a[i] == "--info":
            info = True; i += 1
        else:
            i += 1
    hdr = parse(inp)
    fmtname = FMT.get(hdr["fmt"], ("fmt%d" % hdr["fmt"],))[0]
    px = decode_floats(hdr)
    if flip == "vertical":
        w, h = hdr["w"], hdr["h"]
        rows = [px[y * w:(y + 1) * w] for y in range(h)]
        rows.reverse()
        px = [p for row in rows for p in row]
    # srgb-format textures are already display; force direct for them
    cs = "direct" if hdr["fmt"] in SRGB_FORMATS else colorspace
    rgb = to_u8(px, cs, channels)
    write_png(outp, hdr["w"], hdr["h"], rgb, channels)
    print("DECODE %s -> %s  %dx%d fmt=%s(%d) texel=%d cs=%s flip=%s ch=%d  %s" % (
        inp, outp, hdr["w"], hdr["h"], fmtname, hdr["fmt"], hdr["texel"], cs, flip, channels,
        stats(px) if info else ""))


if __name__ == "__main__":
    main()
