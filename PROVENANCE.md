# PROVENANCE

blender-web is a port of Blender to the web (WebAssembly + WebGPU). Everything
above the ported platform layers is Blender's own source, carried from a single
pinned upstream commit. This file documents the per-file provenance convention
and maps ported modules back to their upstream origin.

## The pin

- Upstream: Blender — https://projects.blender.org/blender/blender
- Branch: `blender-v5.2-release` (Blender 5.2 LTS)
- Commit: `fbe6228777e7`  (recorded in `oracle/PIN`)

`upstream/` is a read-only checkout at this pin. Port changes never edit upstream
in place; they live in `patches/`, `source/blender/gpu/webgpu/`, the web
`intern/ghost` files, `platform_web/`, and
`build_files/cmake/config/blender_web.cmake` (drafted at
`patches/blender_web.cmake`).

## Per-file convention

Every file derived from or ported from Blender carries, at its top:

1. The upstream `SPDX-FileCopyrightText` line(s), preserved **verbatim**.
2. Our added `SPDX-FileCopyrightText` line.
3. An `SPDX-License-Identifier` naming the file's true license
   (`GPL-2.0-or-later` for most Blender code; the true upstream license
   otherwise — e.g. `Apache-2.0` for Cycles-derived files).
4. One provenance line citing the upstream path and the pin.

### Template header block

<!-- REUSE-IgnoreStart -->

    # SPDX-FileCopyrightText: <upstream copyright line(s), verbatim>
    # SPDX-FileCopyrightText: 2026 blender-web contributors
    #
    # SPDX-License-Identifier: GPL-2.0-or-later
    #
    # Ported for the web from <upstream/path/to/original> @ fbe6228777e7

<!-- REUSE-IgnoreEnd -->

Use the comment syntax of the target language: `#` for CMake/Python, `//` or
`/* ... */` for C/C++. When a file is derived from more than one upstream file,
list one provenance line per source.

## Module map

Ported modules are recorded here as they land: port path -> upstream origin ->
pin.

| Port module | Upstream origin | Pin |
|---|---|---|
| `patches/blender_web.cmake` | `build_files/cmake/config/blender_lite.cmake` + `build_files/cmake/config/blender_headless.cmake` | fbe6228777e7 |
| `patches/platform_wasm.cmake` | `build_files/cmake/platform/platform_unix.cmake` | fbe6228777e7 |
| `patches/0012-gpu-webgpu-backend.patch` through the current WebGPU patch series | `source/blender/gpu/` frontend + `source/blender/gpu/vulkan/` architecture/model | fbe6228777e7 |
| `platform_web/ghost/GHOST_SystemWeb.{cc,hh}` | `intern/ghost/intern/GHOST_SystemHeadless.hh` + `GHOST_SystemSDL.{cc,hh}` | fbe6228777e7 |
| `platform_web/ghost/GHOST_WindowWeb.{cc,hh}` | `intern/ghost/intern/GHOST_WindowHeadless.{cc,hh}` + `GHOST_WindowSDL.{cc,hh}` | fbe6228777e7 |
| `platform_web/ghost/GHOST_ContextWGPUWeb.{cc,hh}` | `intern/ghost/intern/GHOST_ContextWGPU.{cc,hh}` | fbe6228777e7 |
| `platform_web/ghost/GHOST_EventBridgeWeb.{cc,hh}` and web key/display headers | `intern/ghost/` event/key/window contracts | fbe6228777e7 |
| `platform_web/shell/` | new browser shell and byte bridge; no direct upstream source | fbe6228777e7 |
| `sandbox/m8-staged-deploy/` | new static packaging, cache and verification tooling; no direct upstream source | fbe6228777e7 |
| `patches/0147-gltf-lazy-optional-compression.patch` | `scripts/addons_core/io_scene_gltf2/` optional compression imports | fbe6228777e7 |

The applied production tree is reconstructed from the immutable upstream pin and
`patches/series`; the repository does not edit `upstream/` in place. New browser-only
modules use the per-file project header and identify themselves as new where there is
no upstream file to cite.
