# GPU r57 readback ticket and layer-view hardening

Patch 0138 turns the 0133 fill-late helper into a correctness-capable backend
primitive without changing a public GPU caller. Exact requests now produce unique,
immutable snapshots with explicit Pending, Ready, Failed, and Canceled states.
Successful consume transfers bytes and retires the ticket once; cancel/free are
explicit; pending WebGPU handles and callback state survive wrapper destruction.
Registry publication and polling are mutex-protected for later WM job use.

Cache requests retain the 0133 fill-late behavior, but pending work is never evicted,
ready payloads are count- and byte-bounded, cancel/free clears any identical settled
payload, and exact claimed results are never silently evicted. Ticket allocation skips
live IDs across wrap. In-flight and exact byte/record reservations occur before staging
allocation and are released on every terminal path.

The low-level buffer and texture entry points reject validation-invalid work before
encoding. The checks include CopySrc usage, mapped buffers, offset/copy alignment and
bounds, device maxBufferSize, texture sample count, mip/origin/extent bounds, and an
exact supported format/aspect/texel-block match.

Texture views pin the backing WebGPU texture and flatten nested mip/layer metadata at
creation, so sampled/storage/readback use and an exact ticket can outlive the source and
view wrappers. WGPUTexture::read and its diagnostic path share resolve_read_region(),
including nonzero 2D-array layers, absolute mips, 3D mip depth, and one-byte stencil
copies. The current 1D-array representation is exact only at mip 0; higher mip readback
is rejected rather than copied from an incorrect region.

## Verification

The production source passed a locked native build and a locked shipping wasm build.
The actual Dawn probes passed 2/2 plus the deterministic capacity control. A temporary
bundled-Chromium hook then exercised the production Exact registry using known RGBA8
bytes at 2D-array layer 2, freed the source before kick and the view before completion,
and proved Ready/None, 32-byte exact payload equality, and consume-once retirement.
The hook was removed, the production source hash restored, and the shipping wasm was
rebuilt to its prediagnostic hashes.

The clean principled-default F12 control still records zero readback kicks because two
EEVEE shaders fail before Film::read_pass. Narrow read-entry instrumentation confirmed
that WGPUTexture::read was never entered. This is an honest upstream EEVEE Phase B
blocker and patch 0138 makes no F12 pixel claim.

The final native census is 149 PASS / 7 FAIL / 2 CRASH across 158 tests, with
static_shaders 956/973. The direct I10 control passes, leaving only the known-spurious
human-owed census RED.

## Remaining boundary

Patch 0138 does not add the public asynchronous GPU API or convert Film/F12 callers.
Dependent patch 0143 must complete the full GPU_texture_create_view lifetime contract
for framebuffer attachments, root operations, and correct 1D-array representation
before later caller-acceptance work.

## Selected receipts

The concise evidence index is
`sandbox/gpu-r57-readback-hardening/0138-final-receipt.txt`. Patch integrity and exact
source hashes are in `0138-final-integrity.txt`; the browser payload is recorded in
`browser-layer-view-device-payload.txt`; final artifact hashes are in
`shipping-artifacts.sha256`.
