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

## 9. Phase 2 results (lane r47, 2026-08-09)

Phase 2 was executed to completion. Phase 1's predecessor (r45) died on a session limit, but
the repo carried the work much further than a bare "mid-link" - the audit found the whole
runbook already materialised in the tree (below). This section records the applied-state audit,
the completed build, the measured staging bound, and the live verification.

### 9.1 Applied-state audit (what the tree already had)

- **patch 0127 APPLIED inside `upstream/`**: `git -C upstream apply --check -p1` fails ("patch
  does not apply"), `--check --reverse` succeeds - the definitive already-applied signature. The
  two files it edits (`build_files/cmake/macros.cmake`, `blentranslation/msgfmt/CMakeLists.txt`)
  are in the upstream dirty set. The series rationale entry was still missing and is now appended
  to `patches/series` (r47).
- **`patches/blender_web.cmake`**: `WITH_INTERNATIONAL` flipped `OFF -> ON` with the D-10 rationale
  block. Well-formed, single edit at the localization stanza. (uncommitted; committed by r47)
- **`patches/platform_wasm.cmake`**: a complete `if(WITH_INTERNATIONAL)` block adds the repo-owned
  locale preload root `--preload-file ${BLENDER_WEB_REPO_ROOT}/build-hosttools/locale@/bw/datafiles/locale`,
  with a `FATAL_ERROR` guard if the locale payload is absent. `BLENDER_WEB_REPO_ROOT` is defined
  earlier in the file. Well-formed. (uncommitted; committed by r47)
- **`scripts/build-locale-datafiles.sh`** (new, SPDX header): compiles all 49 `.po` with the native
  host msgfmt into `build-hosttools/locale/<lang>/LC_MESSAGES/blender.mo` + `languages`. The tree
  was already built (49 dirs + the 2,248 B index). `build-hosttools/locale` is gitignored (a build
  artifact, never committed), as is the host msgfmt binary.
- **`sandbox/m8-staged-deploy/stage_pack.py`**: `classify()` extended - `.mo` under
  `/datafiles/locale/*/LC_MESSAGES/` -> DEFER (stage-1); `languages` falls through to KEEP (stage-0).
  Correct. (uncommitted; committed by r47)

Nothing was malformed; the dead lane's edits were kept verbatim.

### 9.2 Build outcome

The build **COMPLETED**, it did not die: `sandbox/i18n-r45/build.log` ends with
`reconfigure rc=0`, `cache WITH_INTERNATIONAL now: WITH_INTERNATIONAL:BOOL=ON`, `ninja rc=0`,
`[2218/2218] Linking CXX executable bin/blender_browser.js`, and `data: 165654323`. The tree's
`build-wasm-windowed-opt/bin/blender_browser.{js,wasm,data}` are that build (data = 165,654,323 B).

**The nested preload mount worked** - the assumed-clean PRIMARY path in section 6, no fallback
needed. `build.ninja` bakes `--preload-file .../build-hosttools/locale@/bw/datafiles/locale`
alongside the read-only `/bw/datafiles` root, and the file_packager manifest inside
`blender_browser.js` lists all **49** `.../LC_MESSAGES/blender.mo` entries plus the `languages`
index. No file_packager rejection of the nested root - open risk #1 is retired.

### 9.3 Staging bound (the D-10 hard promise, measured)

`stage_pack.py --dry-run` on the built monolith, cross-checked by a manifest byte-audit
(`scratchpad measure_stage0_bound.py`, reusing `classify()` unchanged):

| slice | files | bytes | note |
|---|---:|---:|---|
| stage-0 (keep) | 2,817 | 44,339,255 | of which locale = **1 file, `languages`, 2,248 B** |
| stage-1 (defer) | 538 | 119,518,211 | of which locale = **49 `.mo`, 80,448,982 B (76.72 MiB)** |

- **stage-0 growth from i18n = exactly 2,248 B** (the `languages` index). `.mo` catalogs leaked
  into stage-0 = **0**. Baseline (locale removed) stage-0 = 44,337,007 B. The HARD BOUND holds
  exactly: stage-0 grows only by the languages index.
- stage-1 locale delta = +80,448,982 B raw (~13-17 MB brotli), riding with the already-deferred
  CJK fonts. Nothing on the English `--factory-startup` boot path reads a `.mo`.
- **wire-to-interactive delta = +2,248 B** (only stage-0 gates first pixels; the catalogs are
  post-first-pixels).

### 9.4 Live verification (headed node-Playwright, bundled Chromium, port 8130, ?gate DPR 1)

Rig: `sandbox/i18n-r45/capture-i18n.mjs` (r47 enhanced the langswitch mode to enable
`use_translate_interface`/`use_translate_tooltips` before setting the language - `view.language`
alone loads the catalog but the UI stays English without the interface flag). Comparator:
verbatim `sandbox/m4-golden-prep/compare_m4.sh` (`--fail 0.016 --failpercent 1`, exit-code-primary).
Tree at capture: HEAD `f7cf3e0`, upstream 50 dirty files (full patch series + r46 gpu WIP).

- **Splash (a):** `r47-splash_1280x720.png` = **4.54% failing** (41,823 px), **down from the
  pre-fix 17.8%**. FAIL by exit code, but the fix landed: the **"Language: English (US)" row is
  present and correctly positioned**, the whole Quick Setup dialog now matches the golden's row
  layout (the missing row was the driver's own root cause of the 17.8%). The **residual is not
  i18n**: the amplified diff (`r47-splash-diff3x_1280x720.png`, max err at 521,247 = golden
  near-white vs capture dark) localises to a **dark triangular wedge over the splash IMAGE** - one
  triangle of the splash-image quad not sampling its texture. This is a **GPU splash-image draw
  defect** in the current windowed backend state (r44-r2 + r46 gpu WIP linked into this build); it
  is absent from the 3D viewport/UI (workspace is clean, 9.4 below) and touches no i18n code path.
  Flagged for the gpu lane; not in scope to fix here (must not touch r46's gpu WIP).
- **Workspace (b):** `r47-workspace_1280x720.png` = **1.11% failing** (10,270 px), **improved from
  the pre-fix 2.05%** (the 0123 cube std140 fix in tree). Essentially at the AA floor. Cube renders
  correctly (solid + selection outline), full chrome present, no wedge - confirming the wedge is
  splash-image-specific.
- **Language switch (c) - the fidelity proof:** `r47-ja_1280x720.png` shows **real Japanese glyphs
  rendered from Noto Sans CJK**: the viewport header "Add" menu is **追加**, the outliner and
  properties search fields are **検索** (crisp zoom: `r47-ja-glyphs-header-zoom_1280x720.png`,
  `r47-ja-glyphs-search-zoom_1280x720.png`). This exercises the whole pipeline live: native msgfmt
  `.mo` -> preloaded at `/bw/datafiles/locale/ja/LC_MESSAGES/blender.mo` -> `intern/messages.cc`
  reader -> `BLT_pgettext` -> Noto CJK glyph draw. Round-trip: `en_US -> ja_JP -> en_US` restores
  English cleanly (`r47-en-restored_1280x720.png`); the console log shows `BW_LANG set ja_JP` then
  `BW_LANG restored en_US` with no exception. Coverage is partial (追加/検索 translate; File/Edit/
  header labels stay English) because a runtime RNA `view.language` toggle re-translates the
  dynamically-evaluated strings but not registration-cached `bl_label`s without a full script
  re-register; a fully-Japanese UI is the splash "Continue" startup path. This is faithful native
  Blender runtime-toggle behaviour, and the correctness of the translations proves the reader is
  sound (no garbage, right words).
- **Payload numbers (d):** stage-0 before 44,337,007 B -> after 44,339,255 B (delta **+2,248 B**);
  stage-1 locale delta **+80,448,982 B** (76.72 MiB raw); wire-to-interactive delta **+2,248 B**.

### 9.5 Residue / follow-ups

1. **Splash-image GPU wedge** (one triangle of the splash quad not texturing) is the only thing
   keeping the splash comparison above its AA floor. It is a gpu-backend defect, not i18n; owned by
   the gpu lane. The i18n structural fix (Language row) is verified independent of it.
2. **Live staged-fetch capture** (boot the `make_staged_bundle.sh` bundle, switch to `ja` after the
   stage1-loader streams the `.mo`) was not run: the classification is byte-proven (9.3) and the
   monolith proves the reader+font, so the remaining test is the m8 stage1-loader `FS.writeFile`
   delivery timing, which the m8 lane owns. The rig sets language at boot, which would race the
   post-boot stream; a delayed-switch variant is the clean way to add it.
