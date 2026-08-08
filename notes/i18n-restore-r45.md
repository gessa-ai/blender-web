<!--
SPDX-FileCopyrightText: 2026 blender-web contributors
SPDX-License-Identifier: CC0-1.0
-->

# WITH_INTERNATIONAL restoration - lane r45, Phase 1

**Date:** 2026-08-08 - **Branch:** agent/m2.5-python-boot - **Decision:** D-10
(notes/decisions.md) - restore `WITH_INTERNATIONAL` the faithful way rather than register an
`m4-splash-i18n-row` deferral. Upstream pin: `fbe6228777e7`.

This is a **two-phase** lane. Phase 1 (this note) does everything provable without the shared
build tree: builds the native host `msgfmt`, compiles all 49 catalogs, designs the cross-build
seam (patch 0127), proves `bf_blentranslation` compiles under emcc with the flag on, audits the
fonts, and writes the staging plan + Phase 2 runbook. Phase 2 (flipping
`build-wasm-windowed-opt`) is driver-gated and runs the runbook at the bottom.

## Why this is cheap in fidelity terms (the D-10 premise, re-verified)

The splash "Language" row is gated **only** on the compile-time flag:
`upstream/scripts/startup/bl_operators/wm.py:3391` - `if bpy.app.build_options.international:
col.prop(prefs.view, "language")`. `build_options.international` is registered from
`WITH_INTERNATIONAL` (`upstream/source/blender/python/intern/bpy_app_build_options.cc:40`).
English is the source language and loads no catalog, so **the row appears with zero .mo bytes
at boot** - the whole point of D-10. The .mo catalogs only matter if a user actually switches
language, and they ride the staged deploy (below).

Blender 5.2's translation reader is **built-in** - no external gettext/libintl. The
`bf_blentranslation` link set (`upstream/source/blender/blentranslation/CMakeLists.txt:36-43`)
is all internal libs; `WITH_INTERNATIONAL` only adds `intern/messages.cc` (and
`messages_apple.mm`, which is `if(APPLE)` and therefore **excluded on Emscripten**).

## 1. Host msgfmt

**How built.** `msgfmt` is Blender's own `.po -> .mo` compiler
(`upstream/source/blender/blentranslation/msgfmt/msgfmt.cc`). Unlike datatoc/shader_tool it is
not stdlib-only: it links a small slice of blenlib + guardedalloc. Following **ADR-002** (which
already names msgfmt as the third native host tool - "msgfmt adopts the native route when
WITH_INTERNATIONAL returns"), it is built with the host compiler into
`build-hosttools/bin-native/msgfmt` by an extension of `scripts/build-hosttools.sh`.

The minimal native TU closure (linker-driven, then dead-stripped) is **10 TUs**:

- `blentranslation/msgfmt/msgfmt.cc`
- blenlib: `intern/storage.cc` (BLI_file_read_as_lines), `intern/fileops_c.cc` (BLI_fopen),
  `intern/string.cc` (BLI_strdupn), `intern/BLI_linklist.cc`
- guardedalloc: `intern/mallocn.cc`, `mallocn_lockfree_impl.cc`, `mallocn_guarded_impl.cc`,
  `memory_usage.cc`, `leak_detector.cc`

Include dirs: `blenlib`, `intern/guardedalloc`, `intern/atomic`, `intern/eigen`,
`source/blender/makesdna` (DNA_listBase.h), and `-isystem lib/wasm/include` for the two
external headers blenlib pulls: `fmt/ranges.h` (via `BLI_string_ref.hh`, header-only) and
`zstd.h` (via `fileops_c.cc`). Both live in the **repo-local wasm lib bundle**
(`lib/wasm/include`, the same headers the real wasm build uses via `-isystem`), so **no host
package (homebrew/pkg-config) is required**. `fileops_c.cc`'s only zstd *symbol* users are
`BLI_file_zstd_*`, which msgfmt never calls, so `-Wl,-dead_strip` removes them and **libzstd is
not linked** (verified with `otool -L`).

**Proof it works.**
- `ja.po -> ja.mo`: magic bytes `de 12 04 95` = little-endian `0x950412de` (correct GNU .mo).
- Independently parsed by Python's `gettext.GNUTranslations`: **39,269 entries**, header present,
  and real translations (`Object -> オブジェクト`, `Material -> マテリアル`, `File -> ファイル`).
- Cross-checked against **system GNU gettext `msgfmt`**: it reports "39268 translated messages"
  (+1 header = 39,269), exactly matching. Our .mo is 3,888,616 B vs GNU's 4,098,019 B; the delta
  is only the optional hash table, which Blender's msgfmt writes as zero (msgfmt.cc:185-186) and
  which readers do not need. Content is identical.
- End-to-end via the shipped `scripts/build-hosttools.sh` recipe (isolated run): `fr.po` ->
  39,343 entries, `Object -> Objet`.

## 2. Catalog cost + runtime tree

All **49** `.po` compiled with the host msgfmt. Per-language `.mo` bytes are in
`sandbox/i18n-r45/mo-sizes.tsv`. **Total = 80,448,982 B = 76.72 MiB.** Top-5 largest:

| lang | .mo bytes |
|---|---:|
| ka | 6,125,178 |
| ta | 6,027,463 |
| ru | 4,848,629 |
| ur | 4,241,626 |
| vi | 3,986,323 |

Compression (deferred wire cost): `ja.mo` brotli-q11 = 817,315 B (21% of raw); the full 49-set
gzip-9 = 23.6 MB (29%), so **~13-17 MB brotli** for the whole set. Realistic per-user cost is
**one** language on demand (English = 0).

**Runtime tree Blender expects** (evidence, all in `blentranslation/`):

```
datafiles/locale/
  languages                              <- from upstream/locale/languages (2,248 B)
  <lang>/LC_MESSAGES/blender.mo          <- one per language; <lang> = the .po basename
```

- domain -> filename: `intern/messages.cc:465` `const std::string filename = domain_name + ".mo";`
  with `TEXT_DOMAIN_NAME "blender"` (`BLT_translation.hh:13`) => `blender.mo`.
- directory: `intern/messages.cc:537` `search_path + "/" + lang_folder + "/LC_MESSAGES"`.
- search path: `intern/blt_lang.cc:260` `messagepath = BKE_appdir_folder_id(BLENDER_DATAFILES,
  "locale")` => `<datafiles>/locale`.
- languages index: `intern/blt_lang.cc:73` + `BLI_path_join(..., "languages")` =>
  `<datafiles>/locale/languages`, read by `fill_locales()` at `BLT_lang_init` (boot).

`<lang>` matches the `.po` basename directly (`ja`, `zh_HANS`, `sr@latin`, `pt_BR`, ...); the
`lang_folder` construction in `messages.cc:505-528` reproduces exactly that naming (including
the `zh_HANS` uppercase-script special case at :505).

## 3. Cross-build seam (patch 0127)

**What `WITH_INTERNATIONAL=ON` does to the cross build.** The `locales` custom target
(`upstream/source/creator/CMakeLists.txt:523-540`) runs `msgfmt_simple()` per `.po`.
`msgfmt_simple` (`upstream/build_files/cmake/macros.cmake:1238`, invoke at :1261) execs
`env ${PLATFORM_ENV_BUILD} "$<TARGET_FILE:msgfmt>" <po> <mo>` with `DEPENDS msgfmt`. Under
Emscripten `$<TARGET_FILE:msgfmt>` is a `.wasm`/`.js`, and the command runs it **directly** -
it prepends **no** `${CMAKE_CROSSCOMPILING_EMULATOR}` (unlike makesdna/makesrna, which patch
0003 wired for node). So the build **breaks** the moment the `locales` target runs, and
`DEPENDS msgfmt` additionally forces a full emcc link of the never-used wasm msgfmt executable.

**The fix (minimal, mirrors patch 0007).** In `msgfmt_simple`, select
`${BLENDER_WEB_HOST_TOOLS_DIR}/msgfmt` when cross-compiling (set by `platform_wasm.cmake`), else
the in-tree `$<TARGET_FILE:msgfmt>` (native builds unchanged); and change `DEPENDS msgfmt` to
`DEPENDS ${_bw_msgfmt}` so nothing pulls the wasm target. Plus a
`if(COMMAND blender_web_host_tool) blender_web_host_tool(msgfmt) endif()` guard in
`msgfmt/CMakeLists.txt` for parity with datatoc/shader_tool (no-op unless `all` is built).

**Status: patch 0127 PREPARED** (`patches/0127-hosttools-native-msgfmt-wasm.patch`).
`git apply --check -p1` passes against pristine upstream, and a forward/reverse round-trip in a
throwaway copy verified it is cleanly reversible. **Not applied** to the shared upstream in
Phase 1 - it is exercised only by the Phase 2 reconfigure. (0128 held in reserve, unused.)

## 4. Compile proof - bf_blentranslation under emcc

**Method.** Rather than a fresh multi-GB scratch configure (which would regenerate makesdna/
makesrna and contend for the shared ninja lock, on a disk that has been blocked twice with two
gpu lanes actively building), I compiled the **exact** `WITH_INTERNATIONAL`-affected TUs under
`em++` using the shared tree's **own** build flags (DEFINES/INCLUDES/FLAGS extracted read-only
from `build-wasm-windowed-opt/build.ninja`) plus `-DWITH_INTERNATIONAL`, writing objects only to
the sandbox. This compiles the real code path with the real generated headers and is a stronger,
disk-safe proof than re-running a configure whose result is mostly makesrna.

**Result** (`sandbox/i18n-r45/emcc-proof/`): all three TVs that change under the flag compile to
WebAssembly objects -

- `messages.cc.o` = 79,084 B (the `.mo` reader - the only TU `WITH_INTERNATIONAL` *adds*)
- `blt_lang.cc.o` = 16,787 B (its `#ifdef WITH_INTERNATIONAL` locale-init paths)
- `blt_translation.cc.o` = 4,058 B (its `#ifdef WITH_INTERNATIONAL` pgettext paths)

Confirms: **no external gettext dependency**, `messages.cc` compiles clean under emcc, the built-in
reader has no emcc-hostile POSIX/locale calls. Disk high-water mark: **0 growth** (`df -g` 35 GB
before and after). Shared tree not mutated. `EMSDK_PYTHON` was exported per the toolchain
requirement.

(A full scratch `ninja bf_blentranslation` remains available as belt-and-suspenders if the driver
wants it in Phase 2, when the tree is being rebuilt anyway; it was deliberately skipped in Phase 1
for disk safety, which the lane brief flags as the dominant constraint.)

## 5. Fonts - CJK verdict

`upstream/release/datafiles/fonts/` holds **25 real `.woff2` files** (no git-lfs: `.gitattributes`
has no `filter=lfs`; smallest file is 18,312 B, far above a ~131 B pointer). The international
stack is enumerated in `blf_font.cc:2141+`. The CJK font it names, **`Noto Sans CJK
Regular.woff2`, is a real 11,425,316 B file** (10.9 MiB); Arabic/Hebrew/Thai/Devanagari/etc. are
all real too. **A faithful Japanese/Chinese switch test is possible in Phase 2.** Fonts install
**unconditionally** (`creator/CMakeLists.txt:517-521`, not gated on WITH_INTERNATIONAL), so i18n
adds **no** font payload, and they are already classified DEFER -> stage-1 in the staged deploy
(notes/m8-staged-deploy.md:69,78).

## 6. Staging plan

The wasm build preloads datafiles straight from the **read-only** source tree
(`platform_wasm.cmake:325,334`: `--preload-file .../upstream/release/datafiles@/bw/datafiles`),
and `upstream/` is pinned/read-only, so the compiled `.mo` **cannot** be dropped into
`upstream/release/datafiles/locale/`. They ride a **repo-owned** locale tree mounted at
`/bw/datafiles/locale` (which `BKE_appdir(BLENDER_DATAFILES,"locale")` resolves to).

- **Stage-0 (boot):** + `datafiles/locale/languages` only = **2,248 B** (so the language menu is
  fully populated at `BLT_lang_init`). Boot payload growth is effectively zero.
- **Stage-1 (deferred, after first pixels):** + the 49 `blender.mo` = **76.72 MiB raw
  (~13-17 MB brotli)**, joining the already-deferred CJK fonts. Nothing on the English
  `--factory-startup` boot path reads a `.mo`, so wire-to-interactive is unchanged.
- `sandbox/m8-staged-deploy/stage_pack.py` `classify()` extends by: `datafiles/locale/*/LC_MESSAGES/blender.mo`
  -> **DEFER**; `datafiles/locale/languages` -> **KEEP**.
- **Ideal refinement** (m8 residual #2, on-touch WasmFS-fetch backend): fetch a language's `.mo`
  only when that language is picked - then realistic transfer is 0 (English) or one catalog
  (~0.8 MB brotli). The bulk stage-1 stream is the conservative baseline.

## 7. Phase 2 runbook (driver GO)

All commands run from repo root. `export EMSDK_PYTHON=/Users/paws/blender-web/tools/emsdk/python/3.13.3_64bit/bin/python3` first.

```
# (a) Native host msgfmt into build-hosttools/bin-native/ (idempotent; already present from P1).
scripts/build-hosttools.sh

# (b) Apply the msgfmt native-seam patch (via the repo's patch-apply mechanism / same path 0001-0066 use).
#     Verify first: git -C upstream apply --check -p1 patches/0127-hosttools-native-msgfmt-wasm.patch

# (c) Flip the compile-time flag (the ONLY edit to blender_web.cmake:217):
#     set(WITH_INTERNATIONAL ON CACHE BOOL "" FORCE)

# (d) Build the repo-owned locale datafiles tree (deterministic; independent of CMake):
#     for po in upstream/locale/po/*.po; do L=$(basename "$po" .po);
#       mkdir -p <STAGE>/locale/$L/LC_MESSAGES;
#       build-hosttools/bin-native/msgfmt "$po" "<STAGE>/locale/$L/LC_MESSAGES/blender.mo"; done
#     cp upstream/locale/languages <STAGE>/locale/languages
#     (recommend wrapping this as scripts/build-locale-datafiles.sh with an SPDX header.)

# (e) Add a locale preload root in platform_wasm.cmake (repo-owned), gated on WITH_INTERNATIONAL,
#     next to the existing datafiles root (~line 334):
#        --preload-file <STAGE>/locale@/bw/datafiles/locale
#     PRIMARY: nested mount (no font duplication). FALLBACK if emscripten rejects a preload root
#     nested under /bw/datafiles: stage a COMBINED dir (copy upstream/release/datafiles + the
#     locale tree) into a repo-owned dir and point the single existing datafiles root at it.

# (f) Reconfigure + build the shared windowed-opt tree (existing procedure; ninja via the lock):
#     emcmake cmake -S upstream -B build-wasm-windowed-opt -C patches/blender_web.cmake <windowed-opt flags>
#     scripts/ninja-locked.sh -C build-wasm-windowed-opt blender_browser

# (g) Extend stage_pack.py classify() (DEFER .mo, KEEP languages), then rebuild the staged bundle:
#     sandbox/m8-staged-deploy/make_staged_bundle.sh --copy

# (h) Verify: re-measure the splash golden (expect the 17.8% -> ~2% class, the missing "Language"
#     row restored) and drive a JA (and ZH_HANS) language switch, confirming CJK glyphs render
#     (the real Noto Sans CJK font is present).
```

## 8. Open risks / residue

1. **Nested preload mount** (`/bw/datafiles/locale` under `/bw/datafiles`) is the assumed-clean
   path; if emscripten's file_packager rejects nested roots, use the combined-dir fallback in
   step (e) (costs ~30 MB of duplicated fonts in the assembly, stripped again by the stager).
2. **`languages` in stage-0 vs the menu:** kept in stage-0 so `fill_locales()` populates the full
   language enum at boot. If a future trim wants it out, English still displays (enum item 0), but
   the dropdown would be English-only until stage-1.
3. **Big stage-1:** +76.72 MiB raw is a large bulk stream. Fine for the post-first-pixels model,
   but the on-touch refinement (risk-free, per-language) is the right end state (item 6).
4. **msgfmt host headers:** the recipe depends on `lib/wasm/include` (fmt + zstd). That dir is a
   required part of the wasm build environment already, so this adds no new external dependency;
   the script errors clearly if it is absent.
5. **Full `ninja bf_blentranslation`** was not run in Phase 1 (disk); the flag-accurate TU compile
   stands as the proof. Belt-and-suspenders full-lib build is a cheap add during the Phase 2
   rebuild if desired.
