#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Fast, semantics-preserving custom-section filter for a wasm module. Copies every
# section verbatim EXCEPT custom sections whose name matches a drop rule. Used to
# strip DWARF (.debug_*) cheaply (byte copy, no wasm-opt parse of a ~900 MB module)
# and, separately, to strip the `name` section to emulate a -g0 wire binary.
#
# Usage: wasm_section_filter.py IN OUT --drop-prefix .debug_ [--drop-name name] ...
import sys

def uleb(b, p):
    r = 0; s = 0
    while True:
        x = b[p]; p += 1; r |= (x & 0x7f) << s
        if not (x & 0x80): break
        s += 7
    return r, p

def main():
    inp, out = sys.argv[1], sys.argv[2]
    drop_prefix = []; drop_name = []
    i = 3
    while i < len(sys.argv):
        if sys.argv[i] == '--drop-prefix': drop_prefix.append(sys.argv[i+1]); i += 2
        elif sys.argv[i] == '--drop-name': drop_name.append(sys.argv[i+1]); i += 2
        else: i += 1
    data = open(inp, 'rb').read()
    assert data[:4] == b'\x00asm', 'not a wasm module'
    o = bytearray(data[:8])  # magic + version
    p = 8; kept = 0; dropped = []
    while p < len(data):
        sec_start = p
        sid = data[p]; p += 1
        size, p = uleb(data, p)
        body_start = p; end = p + size
        drop = False
        if sid == 0:  # custom
            nlen, q = uleb(data, body_start)
            name = data[q:q+nlen].decode('latin1')
            if any(name.startswith(pf) for pf in drop_prefix) or name in drop_name:
                drop = True; dropped.append((name, end - sec_start))
        if not drop:
            o += data[sec_start:end]; kept += 1
        p = end
    open(out, 'wb').write(o)
    sys.stderr.write(f"[filter] {inp} -> {out}: kept {kept} sections, dropped {len(dropped)}\n")
    for n, sz in dropped:
        sys.stderr.write(f"[filter]   dropped custom '{n}' ({sz:,} B)\n")
    sys.stderr.write(f"[filter] in {len(data):,} B -> out {len(o):,} B\n")

if __name__ == '__main__':
    main()
