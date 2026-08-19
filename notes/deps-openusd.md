<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# OpenUSD 26.03 core under Emscripten

Status: **working**. OpenUSD 26.03 builds unpatched with its official Emscripten
profile and a real `UsdGeomMesh` `.usda` save/reopen/value round trip passes under
`-pthread -sPROXY_TO_PTHREAD`.

The reproducible build is `scripts/deps/openusd.sh`; the independent build receipt
is `sandbox/m7-usd-prep/build_receipt.json`.

## Pin and licenses

- OpenUSD `v26.03`, MD5 `cc6d6bffdcdd038f60e2fe4726b08673`, SHA256
  `590ea75ffa3ac0c35fdd080df04d61a696733b8f3d6a79bdc3f13f8077162d36`.
- License: Tomorrow Open Source Technology License 1.0. The full upstream
  `LICENSE.txt` and required `NOTICE.txt` are harvested to
  `lib/wasm/share/licenses/OpenUSD-26.03/`.
- oneTBB `v2022.3.0` is the existing shared Wasm dependency (Apache-2.0).
- zlib comes from Emscripten 6.0.5's `--use-port=zlib` recipe; do not add a second
  independently linked zlib archive to the OpenUSD target.

## Capability profile

The build is static and monolithic (`usd_m` plus the static `usdShaders` plugin).
Python bindings, Imaging, USD Imaging, Hydra consumers, MaterialX, tools, tests,
examples and dynamic plugins are disabled. Blender therefore enables core USD IO
with two explicit capabilities off:

- `USD_HAS_IMAGING=OFF`: authored `UsdGeomMesh` IO works; procedural implicit
  shapes import as transforms because their triangulation adapters live in
  `usdImaging`.
- `USD_HAS_PYTHON_HOOKS=OFF`: Blender's ordinary USD import/export works; pxr
  Boost.Python hook callbacks report unavailable if an add-on registers one.

Native builds default both capabilities on, so the constrained path does not
change the desktop feature set.

## Consumer contract

OpenUSD installs `pxrConfig.cmake` at the prefix root. Emscripten's CMake root-path
policy hides that location unless the consumer sets `pxr_DIR` explicitly and uses
`NO_CMAKE_FIND_ROOT_PATH`.

Link `usdShaders`, not the bare `libusd_m.a`. The imported target whole-archives
`usd_m` and propagates the `/usd` schema and `plugInfo.json` resource options. The
standalone proof intentionally consumes this exact target. For Blender's browser
target, the platform removes only those generated `--embed-file` options and
preloads the complete installed `lib/usd` tree once at the identical `/usd` paths;
Emscripten 4+ rejects mixing embed and preload modes in one link. The stage packer
then defers `/usd/**` until Stage 1 because USD operators are post-boot product
actions. OpenUSD's config also applies `PXR_STATIC` directory-wide; the Blender
platform removes that global definition and attaches it to the `usdShaders`
consumer interface so unrelated Blender translation units do not change ABI flags
or rebuild.

The frozen browser integration receipt is
`sandbox/m7-usd-prep/browser-roundtrip/preview0-final-m7-usd-r1/receipt.json`:
`bpy.ops.wm.usd_export` emits a 1,277-byte ASCII layer, the source object is
deleted, and `bpy.ops.wm.usd_import` restores the exact three vertex values and
triangle topology. The default native capability receipt is
`sandbox/m7-usd-prep/native-capability/preview0-final-m7-native-usd-r1/receipt.json`.

OpenUSD also has a packaging wrinkle: `cmake --install --prefix` relocates its
headers, archives, resources and targets but not its root `pxrConfig.cmake`. The
dependency script installs to staging and explicitly harvests that file, avoiding
an accidental build-directory reference.
