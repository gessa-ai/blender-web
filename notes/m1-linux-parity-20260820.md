<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# Linux M1 parity preflight — 2026-08-20

## Outcome

The dedicated Release parity trees are built and Ninja-clean on ornith-lab. Native and Wasm
enumerate the same 1,667 BLI tests and the same single bmesh-core test, byte-for-byte and in the
same order. Fresh direct execution is all-pass on both platforms:

| suite | native | Wasm | manifest SHA-256 |
|---|---:|---:|---|
| BLI | 1,667/1,667 | 1,667/1,667 | `8aad6b84e6439ced72cad8272870ae2ae74d4905117172d0c2ed903b3063c945` |
| bmesh core | 1/1 | 1/1 | `88f9d8b3d2354eef2f5f0a0ec930d754015ccfbebb253dd2f8ad8b006b5d5601` |

All four list commands and all four execution commands wrote zero bytes to stderr. The parsed
gtest JSON counters and occurrence-preserving result keysets equal the enumerated manifests;
there are zero failures and zero crashes. This is a Linux tier-(a) preflight, not a strict M1
receipt and not a harness PASS.

## Artifact and build evidence

Both trees use Ninja, Release, `WITH_GMP=OFF`, `WITH_TESTS_SINGLE_BINARY=ON`, and
`WITH_TESTS_BMESH_CORE_PARITY=ON`. The Wasm tree uses the pinned Emscripten toolchain. Every
build and dry-run used `scripts/ninja-locked.sh`.

- native build: `ledger/buildlogs/20260820T051813.log`, 329 seconds
- Wasm build: `ledger/buildlogs/20260820T052505.log`, 396 seconds
- final locked dry-runs: native and Wasm both print exactly `ninja: no work to do.`
- native `BLI_test`: `247301e250b74de99999c209d15a28760e915674ce5ae772d17e32ecb2613293`
- native `bmesh_core_test`: `4727cf409e757831cdfdb63172e92deb7b7e98dcaa74c01bf55a924af7e05512`
- Wasm `BLI_test.js` / `.wasm`: `2b2065642a9877156f4d4b05892ef85ec3ea110974a17f08b17787d8670ec019` /
  `1ea38c9c380ceb1f787056bf7e69b569d8ef3d904f49fa96991664bcdff1b0f4`
- Wasm `bmesh_core_test.js` / `.wasm`:
  `e12dabea059273e80f1f683e14a25403f6dd82bd10bd6fedf1cf8ba7b573a9dd` /
  `c988c01ff6b2b81bf8481f488768076a54eb576dc9f9359da44518e1f32a5cbc`
- Node-loadable `blender.js` / `.wasm`: `f1028f32d1682a1f76d42efa21735dbc19ea195e0c770de7e55c8c440985ff19` /
  `de05586d625b67a0ab759f87b02c428a05b3dfc1d5562ea3db11d20c96a62fa0`

The direct-result JSON SHA-256 values were, respectively, native/Wasm BLI
`904dd3a8fe1ef85bb9d7b7ea1ba3aa97d12c2ca5a9ad5744a53b1e0b19a229c9` /
`b744301a20f5732932eae4c7a881ed8cb230bc73d97f1a12a36b96d5ceeb12dc` and native/Wasm bmesh
`81c9605663b4dcf98d2492564e2adc671cd1f54f82555bb423e41241b0c070b9` /
`d579f90a3ac2482c7f2b7c627380a44a131d012ae9aee6f87b71f513680f82a0`.

## Cold-host defects closed

1. `lib/linux_x64` was at the correct commit but contained Git LFS pointer text. The first native
   link rejected `libOpenImageIO.so.3.1.13` as an unrecognized file format. An explicit
   `git lfs pull` followed by `git lfs fsck` restored the exact payload; the library is now a
   17,677,848-byte ELF and the dependency checkout remains at
   `30d9f881c4b62c52323fd11637eeea56d460e35c`.
2. The Linux host package list omitted `libegl-dev`. Compilation then stopped in
   `GHOST_ContextEGL.cc` at `EGL/eglplatform.h`. Installing that 1.7.0-3 package closed the
   compile seam. Both prerequisites are now explicit in `notes/migration-to-ornith-lab.md`.
3. Direct execution of build-tree native tests requires Blender's bundled-library environment.
   Linux `DT_RUNPATH` is not transitive, so OIIO/OpenEXR/OpenJPH children are found by exporting
   the sorted `lib/linux_x64/**/lib` directories through `LD_LIBRARY_PATH`, matching
   `PLATFORM_ENV_BUILD` in `upstream/build_files/cmake/platform/platform_unix.cmake`.

## Strict-receipt blockers left honest

- `freeze_release.py` requires a pristine outer repository. The reconstructed, intentionally
  preserved `OUTER_WORKTREE_REMAINDER` still contains unrelated lane-owned tracked changes, so
  this iteration neither discarded nor bulk-committed them.
- The canonical `oracle/bpy.sh` needs a verified Linux Blender through `BLENDER_BIN`; Docker API
  access is denied to this session. No macOS path or unverified binary was substituted.
- `run_m1.py` and its independent verifier currently invoke raw `ninja -n`. The ornith-lab
  contract permits Ninja only through `scripts/ninja-locked.sh`; therefore the strict runner was
  not invoked. A bounded lock-portability round must update the producer, verifier, and their
  adversarial self-checks together before a fresh receipt is attempted.
