<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M7 OpenUSD 26.03 Wasm closure

Status: dependency, integration, native-capability, and real browser operator proof
complete. This directory does not relax the remaining strict M7 stage/performance/browser
matrix gates.

`configure_receipt.json` and `build_receipt.json` bind the exact archive, configuration,
install, static archives/resources, and passing pthread smoke. The named historical
receipts remain preserved, but strict M7 never selects them by a hard-coded label. A final
browser run and `make_native_receipt.py` each create a fresh label directory containing
an exclusive `receipt.json` plus `selector.json`; the verifier requires exactly one
immutable selector of each kind and rechecks its current build, source-freeze, and producer
bindings.

After the final source freeze and current native/Wasm builds reach a fixed point, publish
the two selectors with the same aggregate label (never reuse a failed label):

```sh
node sandbox/m7-usd-prep/verify_browser_usd.mjs "$FINAL_RUN_LABEL"
python3 sandbox/m7-usd-prep/make_native_receipt.py "$FINAL_RUN_LABEL"
python3 sandbox/m7-product-gate/verify_m7.py --release-label "$FINAL_RUN_LABEL"
```

The browser producer requires the exact development bundle to already be served at
`BW_BASE` (default `http://127.0.0.1:8165`). The native producer does not build: it refuses
publication unless locked `ninja -n bf_io_usd` is already at an exact no-work fixed point.

## Decisive result

OpenUSD 26.03 has an official Emscripten target. Blender already pins the same release:

- archive: `https://github.com/PixarAnimationStudios/OpenUSD/archive/v26.03.tar.gz`
- MD5: `cc6d6bffdcdd038f60e2fe4726b08673`
- OpenUSD license: `TOST-1.0` (full `LICENSE.txt` and `NOTICE.txt` must ship)
- existing oneTBB: `v2022.3.0`, MD5 `2b242c465b194ac8e1451ea1354873ae`,
  Apache-2.0
- Emscripten 6.0.5's `--use-port=zlib`: zlib `1.3.2`, port SHA-512
  `16fea4df307a68cf0035858abe2fd550250618a97590e202037acd18a666f57afc10f8836cbbd472d54a0e76539d0e558cb26f059d53de52ff90634bbf4f47d4`,
  Zlib license. OpenUSD's Wasm recipe supplies this compiler/link spell even though its
  core-only dependency resolver does not build a separate zlib. Blender also already pins
  zlib `1.3.1`; the final integration must resolve to one provider and retain its notice.

The exact archive configured successfully against `lib/wasm` in 2 seconds without an
OpenUSD source patch. The generated product is the static `usd_m` target
(`libusd_m.a`). The complete install also builds the static `usdShaders` plugin. The
official Emscripten CMake interfaces embed `plugInfo.json`, generated schema files, and
shader resources under `/usd`; a bare archive link is therefore incorrect. Consumers
must link the installed `usdShaders` target, which whole-archives `usd_m` and preserves
those resource flags.

The configured core comprises 668 object files across 30 components. Largest measured
components are `sdf` 99, `tf` 81, `usd` 58, `gf` 57, `usdGeom` 41, `pcp` 39,
`trace` 27, `usdLux` 25, `arch` 23, `usdVol` 21, `ar`/`usdSkel`/`usdPhysics` 20 each,
and `usdUtils` 19. The configure receipt's `ninja -n install` has 1,693 commands total:
the final commands build the `usdShaders` objects, link `libusd_m.a` and
`libusdShaders.a`, then install.

## Reproduce without touching the shipping prefix

```sh
sandbox/m7-usd-prep/run_openusd_wasm.sh \
  --archive /tmp/usd-v26.03.tar.gz \
  --work /tmp/openusd-wasm-2603 \
  --mode configure

# Once a build slot is available:
sandbox/m7-usd-prep/run_openusd_wasm.sh \
  --archive /tmp/usd-v26.03.tar.gz \
  --work /tmp/openusd-wasm-2603-smoke \
  --mode smoke --jobs 8
```

The script fails closed on the source hash, an existing work path, missing Wasm oneTBB,
configure/build errors, absent installed artifacts, plugin/resource link errors, and any
`.usda` mesh value mismatch. `USD_CORE_SMOKE_OK` is the only success terminus.

## Feature profile and honest boundary

Enabled: core `arch/tf/gf/js/trace/work/plug/vt/ts`, asset resolution and composition
(`ar/kind/sdf/pcp/usd`), geometry/material/light/skeleton schemas, `usdUtils`, static
monolithic registration, `.usda/.usdc/.usdz` file-format code, safety checks, threads,
and exceptions.

Disabled by the official Wasm posture: Python bindings, Imaging/USD Imaging/Hydra,
validation, command-line tools, examples/tutorials, MaterialX, OpenVDB, Alembic, Draco,
OIIO/OCIO, PTex, GL/Metal/Vulkan, Embree, and RenderMan. This profile is enough for a
real mesh operator round-trip but is not feature parity with desktop USD.

Three current Blender assumptions prevent simply flipping `WITH_USD`:

1. `intern/usd_precomp.hh` unconditionally includes Hydra `hd` headers.
2. `intern/usd_reader_shape.cc` uses six USD Imaging adapters to tessellate implicit
   sphere/cube/cone/cylinder/capsule/plane prims.
3. `intern/usd_hook.cc` uses OpenUSD's Boost.Python layer, which does not exist when
   OpenUSD Python support is off.

Regular `UsdGeomMesh` import/export does not require any of those three features.

## Implemented patch boundaries

1. Dependency lane: promoted the driver into `scripts/deps/openusd.sh`, installed only
   after its isolated smoke passes, register it after oneTBB, and harvest
   `include/`, `lib/libusd_m.a`, `lib/libusdShaders.a`, `pxrConfig.cmake`, `cmake/`,
   `lib/usd/`, `plugin/usd/`, `LICENSE.txt`, and `NOTICE.txt`.
2. CMake lane: `patches/platform_wasm.cmake` uses
   `find_package(pxr CONFIG REQUIRED PATHS "${_bw_libwasm}" NO_DEFAULT_PATH)`, set
   `USD_INCLUDE_DIRS=${PXR_INCLUDE_DIRS}`, `USD_LIBRARIES=usdShaders`,
   `USD_LIBRARY_DIR=${_bw_libwasm}/lib`, and `USD_FOUND=ON`. Do not use only the
   archive path because that drops whole-archive and `/usd` resource link options.
   `WITH_USD` is on; Hydra and MaterialX remain off.
3. Blender core-profile lane: `USD_HAS_IMAGING` and `USD_HAS_PYTHON_HOOKS`
   compile-time capabilities. Exclude the two `hd` PCH includes when Imaging is absent.
   In the no-Imaging profile, omit `usd_reader_shape.cc` and make
   `usd_reader_stage.cc` report unsupported implicit-shape prims while preserving
   `UsdGeomMesh`. In the no-Python-profile, compile an explicit hook stub that preserves
   required C/RNA symbols, reports that hooks are unavailable, and never claims callback
   success. Do not silently pretend either feature works.
4. Integration proof lane: built `bf_io_usd` and the browser executable. In browser,
   create a named triangle mesh, export `.usda`, delete it, import the saved bytes, and
   assert operator availability, non-zero exact output, object/mesh topology, positions,
   transform, material assignment, and a second export that reopens. Follow with `.usdc`
   and `.usdz`; no strict M7 green until all formats claimed by the UI are truthful.
5. Legal/size lane: the public assembler copies OpenUSD/TBB/zlib notices into the preview license
   inventory and bind the dependency hashes. Record archive size and final JS/Wasm/data
   deltas before deciding whether USD belongs in stage 0 or an explicitly loaded module.

## Estimated build DAG

These are planning estimates, not receipts. The only measured timing so far is the
2-second configure and the 668-object/1,693-command graph.

```text
existing Emscripten + oneTBB + zlib
          |
          +--> verify/extract/configure (under 1 min; measured configure 2 s)
                   |
                   +--> OpenUSD core + usdShaders install (15-45 min estimated)
                              |
                              +--> isolated whole-archive smoke (2-10 min)
                                        |
                    Blender capability patch + bf_io_usd compile (5-20 min)
                                        |
                              final Wasm link (10-35 min)
                                        |
                       browser operator round-trips (10-20 min)
```

Critical-path estimate after the source freeze: 42-130 minutes if no new compile error;
reserve half a day for the three known Blender capability edits and link-size iteration.

## Stage-0 first-pixel and 8-second structural fix

The current shell dismisses `#loader` on the first `presentBackbuffer` log or, in normal
mode, unconditionally 2.5 seconds after `WM_main`. Frame 0 is only the persistent
backbuffer's black clear. The verified real UI arrived on frame 1 at 20,847 ms, so the
current handshake calls black pixels success and exposes a black product surface. Stage 1
is already fast and is not the 20-second cause.

The console order gives a smaller root than speculative pipeline work: frame 0 is emitted,
then there is no second present until the Python file bridge eventually logs
`BW-FILEBRIDGE INITIAL-REDRAW`; frame 1 immediately follows and contains the real UI. The
GHOST boot heartbeat currently emits `GHOST_kEventWindowActivate`. Only the first activation
changes window state, so later heartbeat events do not reliably re-tag screen regions. A
plain `WindowUpdate` was previously tried, but its native handler adds only `NC_WINDOW`, not
the `NC_SCREEN | NA_EDITED` notifier needed to redraw region buffers.

Shortest structural patch, without weakening the screenshot oracle:

1. In `GHOST_SystemWeb::processEvents`, replace the bounded activation heartbeat with
   `GHOST_kEventWindowUpdate` while `bw_present_count()<2` (retain a bounded timeout).
2. In `wm_window.cc`'s `GHOST_kEventWindowUpdate` case, add
   `NC_SCREEN | NA_EDITED` only for the Emscripten platform. Frame 0 may be the black
   retained-buffer composite; the forced region redraw produces frame 1 without waiting
   for Python or user input. Stop once the second present is observed.
3. Start Stage 1 as soon as `window.__bwModule.FS` exists, but keep its unpack loop yielded.
   Decouple payload streaming from loader visibility.
4. Poll the existing `bw_present_count` export and keep the visible loader/progress/proof
   surface until count >=2. Remove the 2.5-second unconditional hide. A bounded timeout must
   show a failure state, not reveal black. The verifier still decides success from decoded
   varied/non-black compositor pixels, never from the counter alone.

This is a two-source-file redraw fix plus two shell scheduling changes, and the current
evidence predicts a real frame inside the existing three-second heartbeat window. Rerun the
strict under-eight-second pixel gate before any pipeline refactor. Only if the forced second
draw still exceeds budget should the next discriminator timestamp every synchronous
`CreateRenderPipeline`/`CreateComputePipeline` call during that draw; all current WebGPU
startup pipeline creation is synchronous, but it is not yet proven to account for 20 seconds.
Loader changes alone must never mark the latency gate green.

## Firefox and Safari fallback matrix

Local prerequisites already exist on this Apple-silicon/macOS 26 host: Playwright Firefox
151 and WebKit 26.5 are installed, branded Firefox 143.0.1 is installed, and Safari 26.0
plus `safaridriver` are present. Safari 26 includes WebGPU. Mozilla did not enable WebGPU
by default on Apple-silicon release builds until Firefox 145 on macOS 26 (147 on older
macOS), so the installed branded Firefox 143 row is expected to classify as renderer
unsupported without changing user preferences. File System Access picker APIs are not
portable; OPFS and file-input/download fallbacks remain the contract.

Add a separate `sandbox/m7-browser-fallback/` verifier after the product freeze:

1. Serve the exact immutable bundle with COOP/COEP and bind JS/Wasm/data hashes.
2. For Playwright Firefox and WebKit, record browser/version, secure context,
   `crossOriginIsolated`, `SharedArrayBuffer`, main/worker `navigator.gpu`, adapter/device,
   OPFS, `showOpenFilePicker`, and `showSaveFilePicker` capability probes.
3. Where the editor boots, use a real file chooser event to open a physical `.blend`, save
   through the download fallback, and compare exact bytes/magic. Reload and prove the OPFS
   round-trip. Do not mock picker APIs and do not promote a component-only pass to M7.
4. Where WebGPU or worker WebGPU is absent, emit `renderer_unsupported` and separately test
   only the product-owned input/download/OPFS component. That is useful fallback evidence
   but remains strict RED for a full-editor browser row.
5. Repeat the same capability and physical chooser/download/OPFS sequence in branded
   Firefox and branded Safari via WebDriver. Playwright WebKit is not accepted as a Safari
   substitute. Capture exact browser builds, console/page errors, external requests, and
   file hashes in one fail-closed JSON matrix.

Strict M7 remains red until real USD browser operator round-trips, truthful first UI pixels
under eight seconds, and the branded Firefox/Safari rows have been classified with product
fallback receipts.

## Interaction with the unchanged 15 MB launch gate

The current compressed critical set is 37,840,484 bytes: Wasm 22,428,023, Stage-0 data
15,336,209, and glue 76,252. A second-present redraw can fix the black-frame latency, but it
cannot change that wire total.

The existing `sandbox/m8-wasm-split` prototype already answers the mechanism question. With
Emscripten 6.0.5, `SPLIT_MODULE` demand-loading works under `-pthread`,
`-sPROXY_TO_PTHREAD`, modularized JS-EH, and no JSPI. Its browser receipt passes boot,
proxied-main demand load, and fresh-pthread demand load. It also proves two constraints:

- generated glue needs a one-line `wasmBinaryFile = findWasmBinary()` guard in each pthread
  before the split proxy derives the secondary URL;
- each pthread has its own table and therefore compiles the secondary on first use, so the
  production split should keep demand-loaded UI/import/export boundaries on the WM worker.

The measured subsystem-only split moves 13.29 MB raw to a 2.26 MB-Brotli secondary but leaves
a 19.36 MB-Brotli primary. That cannot reach the total gate. The next decisive build must be
the profile-driven Emscripten flow: link once with `-sSPLIT_MODULE -Wno-experimental`, capture
`__write_profile` after a representative first-frame/first-input workload, merge profiles,
then run `wasm-split --profile` on `.wasm.orig`. The primary target is not 14-15 MB: after
data and glue it must be about 9 MB, with a hard assertion on the combined total.

There is also a concrete data cut available for that experiment. The current Stage-0 keeps
several resources that are not first-frame inputs: the build-only `icons_blend/toolbar.blend`,
`preview*.blend` and `splash.png` copies already compiled into the executable, the authoring
`splash_template.xcf`, all external StudioLights (Solid Workbench has an internal default),
and NumPy's test corpus. `measure_stage0_candidate.py` moves only those behind Stage 1 without
changing the shipping classifier. On the current bytes its fast q5 measurement is
16,855,815 -> 6,222,146 bytes. That is a directional planning receipt, not a substitute for
the serialized release-q11 measurement. The product patch must retain
the strict initial Solid Workbench pixel gate, complete Stage 1 before exercising matcap and
studio-light modes, and rerun all Workbench rows before adopting the cut.

Concrete split patch boundaries after the source freeze:

1. Add a profile-only browser link option next to `_bw_browser_flags` in
   `patches/platform_wasm.cmake`; it appends `-sSPLIT_MODULE -Wno-experimental` and a sandbox
   post-JS profile exporter. Never enable it in the ordinary release configuration.
2. Drive at least default boot/solid first pixels, canvas selection/transform, file bridge,
   and the minimal save/open path. Export each `__write_profile` byte stream and merge with
   `wasm-split --merge-profiles`; preserve the exact `.wasm.orig` from that same link.
3. Split `.wasm.orig` with the merged profile and current module feature flags, name the
   secondary from its placeholder namespace, strip names, and fail if Brotli(primary + glue +
   candidate Stage 0) exceeds 15,000,000 bytes.
4. Carry the proven pthread glue guard as a deterministic post-link transform (or upstream
   Emscripten patch), add the secondary to the service-worker manifest, and show its download
   as post-first-pixel progress. Keep synchronous first-use loading off the browser main
   thread.
5. Run every Workbench/Cycles/files gate plus a many-thread soak. A missing secondary,
   first-use call on the browser main thread, per-thread repeated compilation regression, or
   any profile/byte mismatch is a release failure.

Reproduce the non-mutating data measurement:

```sh
python3 sandbox/m7-usd-prep/measure_stage0_candidate.py --quality 5
# q11 is the release measurement; it is slower and should run in the serialized build slot.
python3 sandbox/m7-usd-prep/measure_stage0_candidate.py --quality 11
```
