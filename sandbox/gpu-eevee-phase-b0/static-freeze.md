<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# 0146 static freeze receipt

Date: 2026-08-09

Baseline HEAD: `5631379defb51b4beb92e284edaba655400f4803`

Patch: `patches/0146-gpu-eevee-shadow-tag-readonly.patch`

Patch SHA-256: `986f95b9d3645c4fffc1cfc65e1d0b7fcce09ca7ef7605b991e2e54ba4613899`

Note SHA-256: `1d142113f0e9dba85e7e0e5b27328c574e86907b5c5b6c3ddbbe88d82f4ddeed`

Probe plan SHA-256: `cbf7a0114ce9d8fda202df5a215db61ae1a9f1ad89a2c650d6f2ff03b6d6744a`

## Source identity

Live baseline source SHA-256:

```text
04be244d8d05c2ae09b0124ec5ef4f30a6817144b441f5fb79ad5717d560dc59  source/blender/draw/engines/eevee/shaders/eevee_shadow_tag_update.bsl.hh
```

Isolated patched source SHA-256:

```text
aafa6f6223107d3fa532b8ccfaec6a61aa0bac833e0b8e9856fac4b9fae7bfba  source/blender/draw/engines/eevee/shaders/eevee_shadow_tag_update.bsl.hh
```

The patch passed a read-only forward apply-check with whitespace errors enabled against the live
baseline. In `/tmp/blender-web-0146.b3mG3D`, the current patch reversed the applied source to the
exact baseline SHA-256 and reapplied it to the exact patched SHA-256.

Static inspection confirmed that the local slot-8 table is read-only, only the vertex and fragment
tag-update entry points use it, `tag_propagate` retains generic read-write `TileMaps`, and the
slot-9 `Tiles` atomics remain unchanged. The patch reports one source path, 6 insertions, and 2
deletions.

The live source remained unapplied and unchanged at freeze time. No build or browser run was
performed during the freeze. Runtime, native, and browser acceptance was deferred until
`0138 -> 0143 -> 0144` completed on a stable tree. Phase B1 was not started.

## Post-freeze update, 2026-08-10

The dependency stack is now present and 0146 is applied after 0144. The patch bytes, baseline hash,
and patched hash above are unchanged. Locked native and wasm builds completed, static coverage rose
from 970 / 987 to 971 / 987, and the targeted browser console no longer contains the tag-update
vertex read-write failure. Phase B1 remains separate and still blocks a non-black shadow result.

Updated note, build, census, browser, and replay hashes are in `0146-final-receipt.txt` and
`0146-final-integrity.txt`.
