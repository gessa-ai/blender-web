<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# P0-E resize frame-ownership candidate — 2026-08-27

## Outcome

Commit `efa907a` closes a frame-label race in the complete-resize-frame candidate without changing
GHOST's hardware-known-safe synchronous present boundary. `WGPUContext::sync_backbuffer()` may run
more than once inside one WM frame. It now updates only the episode belonging to the currently
adopted persistent drawable. `WGPUContext::begin_frame()` snapshots that value once into the
frame-bound episode used by `end_frame()` admission. A resize commit followed by a later context
reactivation can therefore no longer relabel old- or mixed-drawable work as the replacement frame.

This is patch 0294. The exact CAPTURE product was relinked from committed `efa907a` and remains
pending the Apple 10/10 semantic-pixel plus independent-receipt bar. Device-free and fallback
evidence below proves frame ownership, replay identity, product shape, and error-free scheduling;
it does not close a hardware pixel defect.

## Experiment and implementation

The fail-first source verifier rejected the prior source at three exact boundaries
(`20260827T180706-2306731`): it had no separately retained adopted episode,
`sync_backbuffer()` wrote directly into `redraw_present_frame_episode_`, and `begin_frame()` did not
capture the adopted value. This mattered because the preceding fallback trace had already proved
that context activation occurs repeatedly inside a single WM frame.

The implementation now has two values:

- `redraw_present_adopted_episode_`, updated atomically with each adopted GHOST backbuffer snapshot;
- `redraw_present_frame_episode_`, copied from the adopted value exactly once at `begin_frame()`.

The queue-tail check continues to use only the frame-bound value. Patch 0294 reverse-applies,
reapplies, and reconstructs both live files byte-for-byte (`20260827T181706-2317121`). Class 128 in
`notes/porting-patterns.md` records the general failure mode.

## Evidence

- Source admission: 82 checks and 50 mutations pass (`20260827T181122-2310350`).
- Canonical clean-pin replay: 271 active patches, 305 canonical paths, snapshot SHA-256
  `984694644c4a...` (`20260827T181122-2310351`).
- Native/wasm32 parity: 59 first-pixel/resize recovery cases are byte-identical and include the
  commit-between-begin-and-reactivation schedule (`20260827T181149-2312552`).
- REUSE 6.2.0 is green at 2,747/2,747 files (`20260827T182434-2322714`).
- Locked CAPTURE relink and committed-state no-work are green
  (`20260827T181725-2317350`, `20260827T181917-2318785`).
- CAPTURE inventory preflight, hardware-producer 42/17 self-check, independent-consumer 2/13
  self-check, capture-profile 21/23 self-check, and eight-source/44-mutation trace contract are
  green (`20260827T181917-2318784`, `2318789`, `2318797`, `2318808`, `2318824`).
- The exact fallback product shrinks and restores with ticks `246/524/617`, presents `16/17/18`,
  episodes `0/1/2`, one admitted present per resized extent, two complete/current/contained/
  VIEW_3D-bound traces, and zero WebGPU rejection or loss (`20260827T181936-2318989`). This is
  diagnostic-only.
- Direct M4 remains RED at the absent exact hardware binding (`20260827T182029-2319638`). The
  authoritative pinned-container regression restores M0 6/6 and retains every named M1-M8
  receipt/APPLY/tier boundary (`20260827T182039-2319723`).

## Exact CAPTURE generation

| Artifact | Bytes | SHA-256 |
| --- | ---: | --- |
| `blender_browser.js` | 707,565 | `52a9a025783071e959daf55d0c07772d9a737220d13b524df9d07abc8ac5f2f0` |
| `blender_browser.wasm` | 120,511,191 | `89acb092bb29a1217d9dcf77b12ae777e785ce4b7fb99473365b9b0f184b7f2e` |
| `blender_browser.wasm.orig` | 119,157,867 | `070b3e89ba7a4f144e63780c10ad7596a5f95b13cf2a370ccfe7ccab1777ab1c` |
| `blender_browser.data` | 168,637,598 | `095d0ba748c3cdc2fcd0956def221e0f0d347d41d95e0a150a28670ab1cea24c` |
| `blender_browser.split-build.json` | 13,251 | `f49b6e9e1c0aec6ebbd4ed5e3b8ef5b25aa4a060b27cee38d1a97c5473fb9567` |

## Incoming predecessor evidence and boundary

While this iteration was relinking, the driver deposited a legacy ten-attempt result under
`~/bw-logs/mac-capture-evidence-20260827-p0e/PASS/`. It reports 10/10 successful zero-input
shrinks, 0 rejects, and 0 page errors; the retained 1100x640 PNG visibly contains the full grid,
shaded selected Cube, camera, light, and navigation gizmo. Its stress result also paints six
shrink/restore extents and changes pixels after orbit. Those files were written before the
`efa907a` relink and carry no product hashes or canonical receipt inventory, so they are strong
pixel evidence for the preceding candidate but cannot bind the new `070b3e89...` generation.

P0-E remains open until the driver runs the repository producer against this exact generation and
the independent consumer emits PASS for all ten attempts. No APPLY product, public bundle, tag,
profile, receipt promotion, result promotion, tolerance, golden, blacklist, deferral, or launch
claim is authorized by this candidate.
