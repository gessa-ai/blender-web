#!/usr/bin/env python3
# SPDX-License-Identifier: CC0-1.0
# Exemplar: extract the seq/VSE functions' actual bytes from the shipped opt
# wasm, concatenate, and report raw size (for brotli). Also resolve nm addr base.
import re, sys
WASM = "build-wasm-windowed-opt/bin/blender_browser.wasm"
NM   = sys.argv[1]
CODE_FOFF = 444151          # file offset of CODE payload (llvm-objdump VMA)
CODE_SZ   = 88706390
seq_rx = re.compile(r"blender::seq::|(^|[^A-Za-z])SEQ_|sequencer|::seq::")
line_re = re.compile(r"^([0-9a-fA-F]+)\s+([0-9a-fA-F]+)\s+([tT])\s+(.*)$")
addrs=[]; seq=[]
mn=1<<62; mx=0
with open(NM,errors="replace") as f:
    for ln in f:
        m=line_re.match(ln)
        if not m: continue
        a=int(m.group(1),16); s=int(m.group(2),16); name=m.group(4)
        if s==0: continue
        mn=min(mn,a); mx=max(mx,a+s)
        if seq_rx.search(name): seq.append((a,s))
print(f"t-sym addr range: min={mn} max_end={mx}")
print(f"CODE file range:  {CODE_FOFF}..{CODE_FOFF+CODE_SZ}  (size {CODE_SZ})")
# decide base: if max_end <= CODE_SZ+slack -> code-relative; else file-absolute
if mx <= CODE_SZ+65536:
    base=CODE_FOFF; print("=> addresses are CODE-RELATIVE; file_off = addr + %d"%CODE_FOFF)
else:
    base=0; print("=> addresses are FILE-ABSOLUTE")
data=open(WASM,"rb").read()
out=bytearray(); tot=0
for a,s in seq:
    foff=base+a
    out+=data[foff:foff+s]; tot+=s
open("seq_bytes.bin","wb").write(out)
print(f"seq/VSE funcs={len(seq)} concat_raw={tot:,} (expect 771,617)")
