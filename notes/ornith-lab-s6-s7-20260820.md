<!--
SPDX-FileCopyrightText: 2026 blender-web contributors
SPDX-License-Identifier: CC0-1.0
-->

# ornith-lab s6 rebuild and s7 preflight

Status (2026-08-20): **STOPPED before M4 receipt.** This is a migration observation,
not a milestone claim. No fresh M4 label, capture, binding, verifier, or
`harness/run.sh --scope m4` invocation was created.

## s6 serialized build

After source materialization from the canonical Blender remote, the existing serialized
run completed without a second build:

- `~/bw-logs/chain4.log` records `CONFIGURE_OK`, then `BUILD OK (419 s):
  scripts/ninja-locked.sh -C build-wasm-windowed-opt blender_browser`, and finally
  `CHAIN4_ALL_OK`.
- The corresponding build receipt is `ledger/buildlogs/20260820T040055.log`.
- The exact toolchain check reports emcc `6.0.5`
  (`1db513782be24469589d7cb8a1f1834e9a33f271`), Node `v22.16.0`, and native build
  Python `3.13.13`.

The product artifact contract required by `notes/migration-to-ornith-lab.md` was then
checked directly:

| path | result | SHA-256 / detail |
| --- | --- | --- |
| `bin/blender_browser.js` | present, 652021 bytes | `acde4b0c74e7a039745fc9b0716c6cf7312ca86441c4964220da491ee7533c86` |
| `bin/blender_browser.wasm` | present, 118043578 bytes | `8a5eefd8753f9be1ee73947b03618aaca58ec9e2bc475285b5b9b9773563b03b` |
| `bin/blender_browser.deferred.wasm` | **MISSING** | required by the runbook; no alternate deferred artifact exists in `bin/` |
| `bin/blender_browser.data` | present, 167143248 bytes | `09e58a25849eb6290a181141f5f83f928f469fe1e4d9fbdba23210bcada5a351` |

This means the s6 compile/link succeeds, but the M4 output-set contract does not. The
runbook explicitly requires stopping on this artifact mismatch; do not substitute the
primary Wasm or fabricate a deferred module.

## m0 proof

With the prescribed `EM_CACHE=$PWD/.ci-cache/emscripten` and
`CCACHE_DIR=$PWD/.ci-cache/ccache`, `bash scripts/ci/m0-basic.sh` completed with
`M0_BASIC_CI_OK`.

## s7 hardware preflight

The M4 capture was not started because it has two independent hard stops:

1. The product set above lacks `blender_browser.deferred.wasm`.
2. The WSL Vulkan loader enumerates only `llvmpipe (LLVM 21.1.8, 256 bits)` as
   `PHYSICAL_DEVICE_TYPE_CPU`, including with the WSLg socket environment supplied
   transiently. The session itself exports neither `DISPLAY` nor `WAYLAND_DISPLAY`.

The RTX 4090 is visible to `nvidia-smi` and `/dev/dxg` exists, but that is not a
hardware WebGPU adapter result. The detailed Vulkan-ICD investigation and its acceptance
criteria remain in `notes/wsl-vulkan-investigation-20260819.md`.

## Resume criteria

Before a new immutable M4 label is used, restore all four product artifacts, enter a
headed WSLg session, and prove that Chromium obtains the RTX-backed hardware adapter.
Only then start the COOP/COEP server, capture, bind, verify, and issue the M4 receipt
through the unchanged harness.

## 2026-08-20 correction: split mode, not an unexplained link omission

The table above observed the bytes correctly, but its interpretation of the missing deferred
module as an independent link discrepancy is superseded. The reconstructed
`CMakeCache.txt` has `BLENDER_WEB_WASM_SPLIT_MODE=OFF`; the locked minimal Emscripten repro in
`sandbox/m4-split-contract/` proves that OFF emits only JS + monolithic Wasm, while
`SPLIT_MODULE` CAPTURE emits the instrumented Wasm + `.wasm.orig` and still no deferred shard.
Only the repository's profile-bound APPLY finalizer may emit `blender_browser.deferred.wasm`.

The cold-start sequence is therefore CAPTURE -> two strict accepted-hardware browser profiles ->
profile union -> APPLY, as corrected in `notes/migration-to-ornith-lab.md`. Because a software
adapter binds no profile receipt, the missing hardware adapter currently blocks both the APPLY
reconstruction and the later pixel receipt. `scripts/windowed-product-preflight.py` reports the
current OFF shape as valid development output but exits 5 when the shipping APPLY shape is
required. No artifact, receipt, or milestone result was changed by this correction.
