<!--
SPDX-FileCopyrightText: 2026 blender-web contributors
SPDX-License-Identifier: CC0-1.0
-->

# r45 Phase-1 evidence log (WITH_INTERNATIONAL restoration)

Reproducible via `scripts/build-hosttools.sh` (host msgfmt) + the runbook in
`notes/i18n-restore-r45.md`. This file records the raw proof outputs.

## Host msgfmt build

Native TU closure (10 TUs), linker-driven then `-Wl,-dead_strip` (no libzstd linked):
`msgfmt.cc` + blenlib{storage,fileops_c,string,BLI_linklist} +
guardedalloc{mallocn,mallocn_lockfree_impl,mallocn_guarded_impl,memory_usage,leak_detector}.
Headers: blenlib, guardedalloc, intern/atomic, intern/eigen, makesdna, `-isystem lib/wasm/include`
(fmt/ranges.h + zstd.h). Output: `build-hosttools/bin-native/msgfmt` (79,864 B).

## Host msgfmt correctness

```
ja.po -> ja.mo : magic = de 12 04 95  (LE 0x950412de, valid GNU .mo)
Python gettext.GNUTranslations(ja.mo): 39269 entries, header present
  Object   -> オブジェクト   (translated)
  Material -> マテリアル     (translated)
  File     -> ファイル       (translated)
GNU gettext msgfmt (cross-check): "39268 translated messages" (+header = 39269) -> MATCH
  our ja.mo = 3,888,616 B ; GNU ja.mo = 4,098,019 B
  delta = optional hash table only (Blender msgfmt writes 0, msgfmt.cc:185-186); content identical
scripts/build-hosttools.sh recipe (isolated run) -> fr.po: 39343 entries, Object -> Objet
```

## Catalog cost (all 49 compiled)

Total .mo = 80,448,982 B = 76.72 MiB. Per-language bytes: `mo-sizes.tsv`.
Top-5: ka 6,125,178 | ta 6,027,463 | ru 4,848,629 | ur 4,241,626 | vi 3,986,323.
Compression: ja.mo brotli-q11 = 817,315 (21%); all-49 gzip-9 = 23,642,642 (29%) -> ~13-17 MB brotli.
languages index = 2,248 B.

## emcc compile proof (bf_blentranslation, WITH_INTERNATIONAL ON)

Method: em++ with the shared tree's real DEFINES/INCLUDES/FLAGS (read-only from
`build-wasm-windowed-opt/build.ninja`) + `-DWITH_INTERNATIONAL`; objects to sandbox only.
`export EMSDK_PYTHON=.../tools/emsdk/python/3.13.3_64bit/bin/python3`.

```
em++ messages.cc        -> messages.cc.o        79,084 B  WebAssembly (wasm) binary module v0x1
em++ blt_lang.cc        -> blt_lang.cc.o        16,787 B  WebAssembly (wasm) binary module v0x1
em++ blt_translation.cc -> blt_translation.cc.o  4,058 B  WebAssembly (wasm) binary module v0x1
```

All three WITH_INTERNATIONAL-affected TUs compile clean under emcc; no external gettext dep.
Disk high-water mark: 0 growth (df -g = 35 GB free before and after). Shared tree not mutated.
(Throwaway .o objects were verified as `WebAssembly (wasm) binary module version 0x1 (MVP)` via
`file(1)`, then deleted to keep the evidence text-only.)

## patch 0127 (native msgfmt seam)

`git -C upstream apply --check -p1 patches/0127-hosttools-native-msgfmt-wasm.patch` -> clean.
Forward/reverse round-trip in a throwaway copy -> reversible, restores pristine. Not applied to
the shared upstream in Phase 1.
