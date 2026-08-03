<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# FreeType 2.13.3 + Brotli 1.0.9 — wasm cross-build notes (M1.8)

Status: **both built OK**, static, `-pthread`, installed to `lib/wasm`.
Scripts: `scripts/deps/brotli.sh`, `scripts/deps/freetype.sh` (idempotent).

## Why these landed on the M1 critical path (they were "deferrable")

`deps.json` classed freetype/brotli as `deferrable_past_m1`. They are NOT:
Blender has **no `WITH_FREETYPE` option**. `platform_unix.cmake` (which
`platform_wasm.cmake` replaces) does `find_package_wrapper(Freetype REQUIRED)`
unconditionally under `if(NOT WITH_SYSTEM_FREETYPE)`, then
`check_freetype_for_brotli()` which `check_symbol_exists(FT_CONFIG_OPTION_USE_BROTLI
...)` and **FATAL_ERRORs** if freetype lacks brotli. So a real configure cannot
complete without a brotli-enabled freetype. There is no feature to switch off —
the honest resolution is to build them, not stub `FREETYPE_LIBRARIES`.

## Brotli (1.0.9)

Pinned from `versions.cmake` (`BROTLI_VERSION`/`BROTLI_HASH`). CMake static build,
`BUILD_SHARED_LIBS=OFF`, `BROTLI_DISABLE_TESTS=ON`, `-pthread`.

**Install trap:** brotli 1.0.9 gates its `install()` rules behind an auto-detected
`BROTLI_BUNDLED_MODE` that resolves ON under emcmake, so `--target install` is a
no-op (`make: No rule to make target 'install'`). The three static archives build
fine; the script **harvests them directly** (`libbrotlicommon-static.a`,
`libbrotlidec-static.a`, `libbrotlienc-static.a`) plus `c/include/brotli/*.h`.
Blender's `FindBrotli.cmake` matches `brotlicommon-static`/`brotlidec-static` +
`brotli/decode.h`, resolved via `BROTLI_ROOT_DIR=lib/wasm`.

## FreeType (2.13.3)

Pinned from `versions.cmake`. Build flags mirror
`build_environment/cmake/freetype.cmake`:
`FT_DISABLE_{BZIP2,HARFBUZZ,PNG}=ON`, `FT_REQUIRE_BROTLI=ON`, `FT_REQUIRE_ZLIB=ON`,
`BROTLIDEC_*` → our brotli, `ZLIB_*` → our zlib (1.3.1). Installs `libfreetype.a`
(no `2ST` postfix — we skip `CMAKE_RELEASE_POSTFIX`, so no harvest rename needed)
and headers under `include/freetype2/`. `FT_REQUIRE_BROTLI=ON` bakes
`FT_CONFIG_OPTION_USE_BROTLI` into the installed `ftoption.h`, which is exactly
what Blender's `check_symbol_exists` probe reads (script asserts this post-install).

## Consumer wiring (platform_wasm.cmake)

Both are resolved by the M1.8 dependency block via CMake's builtin `FindFreetype`
and Blender's `FindBrotli`, seeded with `FREETYPE_LIBRARY` /
`FREETYPE_INCLUDE_DIR_{ft2build,freetype2}` and `BROTLI_ROOT_DIR`.
`check_freetype_for_brotli()` is reproduced verbatim in platform_wasm.cmake (it
lives in platform_unix.cmake, which the wasm branch replaces).
