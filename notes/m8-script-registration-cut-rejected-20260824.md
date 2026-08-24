<!--
SPDX-FileCopyrightText: 2026 blender-web contributors
SPDX-License-Identifier: CC0-1.0
-->

# M8 deprecated Script editor registration cut — rejected 2026-08-24

## Outcome

Do not omit `ED_spacetype_script()` from the windowed product for size. The exact candidate reduced
the raw Wasm by 1,691 bytes but increased the pinned Brotli-q11 release payload by 19,232 bytes.
Because LAUNCH.md gates the compressed interactive payload rather than raw module bytes, the
candidate was rejected and fully removed. The patch series, windowed options, product feature set,
and deferral registry remain unchanged.

The known-good patch-0254 product was rebuilt and restored byte-for-byte at SHA-256
`dc6a78809d45aabafed11e4708f01f3ea9962d380e638d1333a35effcf35d880`, 111,637,460 raw
bytes. No deprecated-Script feature cut ships.

## Question and experiment boundary

The pinned source marks `SPACE_SCRIPT` as deprecated in
`source/blender/makesdna/DNA_space_enums.h`. A fresh pinned native oracle query confirms that the
relevant modern Area RNA enum exposes `TEXT_EDITOR` and `CONSOLE`, but not `SCRIPT`
(`ledger/buildlogs/20260824T072410-3868699.log`). This made its single registration root a plausible
low-risk size experiment without touching the launch-tier Text Editor, Python Console, or Python
runtime.

The temporary candidate:

- declared a default-ON `WITH_BLENDER_WEB_SCRIPT` option and forced it OFF only for
  `WITH_BLENDER_WEB_WINDOWED`;
- added the corresponding default-ON/native-headless compile definition to
  `bf_editor_space_api`;
- guarded only the one `ED_spacetype_script()` call; and
- retained `bf_editor_space_script`, Script DNA/RNA and blend compatibility, the Text Editor,
  Python Console/runtime, and every native/headless registration path.

A fail-first verifier rejected the unchanged stack because the candidate patch was absent
(`ledger/buildlogs/20260824T072344-3868469.log`). The temporary postimage then passed its exact
one-call/two-retained-call boundary, eight mutation controls, and isolated patch round trip
(`ledger/buildlogs/20260824T072605-3870542.log`). The verifier and candidate patch were removed
after the size metric rejected the experiment; they are not shipping tests or patch history.

## Exact size evidence

Both rows use emsdk Node 22.16.0 and the same whole-module `zlib.brotliCompressSync` transform with
`BROTLI_PARAM_QUALITY=5` and the release metric `BROTLI_PARAM_QUALITY=11`.

| module | SHA-256 | raw bytes | q5 bytes | q11 bytes |
|---|---|---:|---:|---:|
| patch-0254 baseline | `dc6a78809d45aabafed11e4708f01f3ea9962d380e638d1333a35effcf35d880` | 111,637,460 | 27,795,458 | 23,484,149 |
| deprecated-Script candidate | `64a2b5c14396c3a71a770159d6c6e4a37fcfabbfa1d7c3ef13e1a41cbc7a37f7` | 111,635,769 | 27,707,818 | 23,503,381 |
| candidate delta | — | **-1,691** | **-87,640** | **+19,232 (regression)** |

The baseline measurement is `ledger/buildlogs/20260824T072622-3870647.log`. The real locked
candidate relink and measurement are `ledger/buildlogs/20260824T072909-3872393.log` and
`ledger/buildlogs/20260824T073006-3873633.log`.

The opposite q5/q11 directions are not an ambiguity: q5 is diagnostic only, while the existing
M8 release decisions and LAUNCH.md payload bar bind q11. Brotli is deterministic for these exact
bytes and parameters. A q11 increase cannot be presented as launch progress.

## Restoration and decision

After rejecting the candidate, its applied postimage, option, numbered patch, series entry, and
temporary verifier were removed. The real browser target rebuilt through the global Ninja lock
(`ledger/buildlogs/20260824T073334-3875512.log`), reproducing the exact baseline hash and raw size.
The follow-up locked dry-run is no-work (`ledger/buildlogs/20260824T073425-3876007.log`).

The unchanged canonical source replay remains GREEN across 261 paths and all 231 active numbered
patches at canonical SHA-256 prefix `0285efe74bff`
(`ledger/buildlogs/20260824T073616-3877455.log`). OFF product preflight binds 647,701 JavaScript
bytes, the restored 111,637,460-byte Wasm, and 167,143,248 data bytes
(`ledger/buildlogs/20260824T073616-3877456.log`). Pinned REUSE 6.2.0 is GREEN for 2,278/2,278
files (`ledger/buildlogs/20260824T073751-3879717.log`).

Required M8 remains honestly RED at its unchanged 25 technical-release boundaries
(`ledger/buildlogs/20260824T073632-3877652.log`). Container-backed regression restores M0 to
6/6 GREEN while M1-M8 retain their existing strict-manifest, split-product, browser, run-label,
hardware, and release boundaries (`ledger/buildlogs/20260824T073638-3877725.log`).

This closes only the deprecated-Script size question. It changes no accepted adapter, profile,
split product, receipt, result promotion, dependency decision, deferral, tolerance, golden,
blacklist, or milestone promise. Mesa dzn and the Windows path were not attempted, and WSL was not
restarted.
