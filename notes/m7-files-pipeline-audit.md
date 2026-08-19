<!--
SPDX-FileCopyrightText: 2026 blender-web contributors
SPDX-License-Identifier: CC0-1.0
-->

# M7 files + pipeline final audit (2026-08-11)

This is a skeptical readback of `GOAL.md:84` against the current product source and
receipts. It does not change an oracle, golden, deferred entry, or pass flag.

## Contract map

| M7 clause | State | Current receipt / exact remaining condition |
|---|---|---|
| WasmFS/OPFS project store | **GREEN (preview subset)** | `bw_mount_opfs()` mounts `/projects`; a fresh Chromium reload then `open_store` reopened the FSA-saved real `.blend` and retained the authored `BW_M7_FSA_SAVE` object. |
| `.blend` open/save | **GREEN (preview subset)** | Real Blender `open_mainfile`/`save_as_mainfile` bytes pass FSA-shaped handles and real upload/download fallbacks. The saved files carry zstd `.blend` magic. The daemon timer is now `persistent=True`, closing the reproduced “first open works, every later command times out” bug. |
| `.blend` physical drag-drop / native picker | **GREEN Chromium; strict matrix YELLOW** | CDP physical drag carried an actual local `.blend`, reached the shipped listener with `Event.isTrusted=true`, and opened into OPFS. Current Chromium exposes both FSA APIs; both shipped calls occur with `navigator.userActivation.isActive=true`, and standards-shaped handles accept the exact bytes. A macOS system dialog cannot be accepted by CDP, and current Firefox/Safari fallback receipts are still absent. |
| OBJ round-trip | **GREEN** | No-shim wasm `wm.obj_import` then `wm.obj_export`: 8 verts / 12 edges / 6 polys / 24 loops; `parse_obj.py` semantic comparison PASS. |
| glTF round-trip | **GREEN** | Patch 0147 makes optional Draco/Meshopt `_ctypes` imports lazy and handles unsupported Emscripten explicitly in product source. With no probe monkeypatch, real wasm `import_scene.gltf`/`export_scene.gltf` is 24 verts / 30 edges / 12 tris / 36 loops and `parse_glb.py` PASS. Bundle slice checker proves all five patched source files are byte-identical to the public stage-0 payload. |
| USD round-trip | **GREEN** | OpenUSD 26.03 core plus `usdShaders` is cross-built and linked with `WITH_USD=ON`. A strict headed-browser receipt proves the real `bpy.ops.wm.usd_export`/`usd_import` operators: a named triangle exports as non-empty `#usda`, is deleted, and returns with all three positions and the face exact. A separate native target build proves default Imaging and Python-hook sources remain enabled. |
| Staged loading | **GREEN functionally; launch budget RED** | 548/548 files and 119,734,668 bytes stream and install byte-exactly. Stage 0 reaches WM_main but its displayed canvas is still black (`stage0_first_pixels=false`); eventual real Blender UI was decoded as 919,631/921,600 nonblack pixels at 20,847 ms, so LAUNCH's <=8 s bar remains hard RED. Raw critical is 143.7 MiB and deferred is 114.2 MiB. |
| Progress UI | **GREEN** | Visible stable-selector UI shows `Downloading assets`, `Installing assets`, and `Assets ready`, with live and final `114.2 / 114.2 MB` counters. The initial loader also carries the local-runtime/offline challenge and desktop/current-Chrome-or-Edge limitation. |
| Service-worker cache | **GREEN** | Content version `dbe5d2eb48ad3c343efb`; Chromium cached all 12 shell/stage0/stage1 assets, made zero external requests, then a real network-offline reload retained COOP/COEP + SAB and reached WM_main in 260 ms. Public `?pyexpr`/`?args` attacks were ignored. |

`sandbox/m7-product-gate/run.sh --subset` is GREEN and is the explicitly caveated
public-preview subset. The default strict verifier and `harness/run.sh --scope m7`
remain RED; they do not substitute that subset for the GOAL.md promise. Exact strict
blockers are: stage-0 product pixels, the <=8 s interactive budget, the <=15 MB
critical-wire budget, and current Firefox/Safari fallback receipts.

USD is now closed by the faithful core-only capability lane. The browser links the
OpenUSD 26.03 monolithic core plus static `usdShaders`, preloads its exact 70-file schema
and plugin resource tree at `/usd`, and defers that resource tree out of Stage 0. Imaging,
Hydra, and Boost.Python are explicit browser omissions rather than unresolved link gaps.
Native builds default those capabilities on; their `bf_io_usd` receipt contains real
`usd_reader_shape.cc` and `usd_hook.cc` objects and no stub.

## New receipts

Staged bundle verification, headed Chromium on localhost: WM_main; public query
execution disabled; 548/548 files and 119,734,668/119,734,668 bytes installed; a
deferred stdlib file byte-identical; real decoded Blender UI; 12/12 cache entries;
offline reload isolated and WM_main in 260 ms; final functional verdict PASS.

Physical files verification: actual local-path `.blend` drag/drop with trusted event;
FSA availability + trusted activation + exact handle acceptance; real input/download
fallbacks; real Blender-compressed save bytes; OPFS persistence through full reload;
zero external requests and zero GPU/page errors. Final verdict PASS.

Wasm OBJ/glTF round-trip:

```text
OBJ_IMPORT_MESH verts=8 edges=12 polys=6 loops=24
OBJ_ROUNDTRIP_OK .../cube-rt.obj 950
GLTF_IMPORT_MESH verts=24 edges=30 polys=12 loops=36
GLTF_ROUNDTRIP_OK .../cube-rt.glb 1944
OBJ_COMPARE ... -> PASS
GLB_COMPARE ... -> PASS
```

Wasm USD round-trip:

```text
USD_BUILD_OPTION true
USD_EXPORT FINISHED bytes=1277 format=#usda
USD_IMPORT FINISHED verts=3 polys=1
USD_VALUE_ROUNDTRIP exact_positions=true exact_face=true
```

Immutable receipt:
`sandbox/m7-usd-prep/browser-roundtrip/preview0-final-m7-usd-r1/receipt.json`.
It binds JS `be22b804…`, Wasm `9f71c526…`, data `7fde0c7d…`, driver source,
Chrome 149.0.7827.55, zero page crashes/errors/external requests/GPU errors, and the
exported file SHA-256 `90fb5af303…`.

Round-trip artifact SHA-256 (temporary receipt):

```text
a05c54c303f85a41663cfd63c25cc4827682f2912233a01476c584999718ea4e  cube-rt.obj
59757ea68d8cd7b74bef727b7003702e194757d32041e98b838c13a5ec80549f  cube-rt.glb
```

Current receipt SHA-256:

```text
01872ff845d1a3ae4a7136f796a9333ee5c14d8dd69134ae4e23d9425ea41e6e  artifacts/verify_staged.json
cf8bceadfb398622cbf7fdb57f84347c746e3b1afa79032671c1d1e1c6411cb1  verify_files.json
e6536ffac02d987d542c312342a35aca567ae0992b8715db8e7b195dc2df8e5d  artifacts/staged_boot_1280x720.png
```

The assembler also now resolves relative `--bin`/`--out` paths before symlinking and
fails the digest if any asset is missing. This closes a reproduced false-success mode:
a relative `--bin` previously produced a broken wasm symlink while still printing an
assembled manifest.
