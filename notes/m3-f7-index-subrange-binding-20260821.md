# M3.F7 indexed-subrange binding parity — 2026-08-21

<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

## Outcome

Patch 0157 closes an indexed-draw state split in WebGPU's multi-viewport path. Blender index
subranges share their parent's GPU allocation, so the subrange start is a bind-time byte offset;
squeezed u16 buffers also retain an inherited base vertex. The ordinary pass applied both values,
but the multi-viewport pass bound offset zero and issued `DrawIndexed` with base vertex zero.
EEVEE shadows and the GPU suite activate multi-viewport rendering; separately, mesh triangle
extractors create index subranges. Live combinations remain hardware-owned evidence.

`index_binding_plan()` now derives those inseparable values once from the real `IndexBuf`
metadata. Ordinary, triangle-fan, and multi-viewport direct draws consume the plan, preventing an
alternate pass encoder from silently dropping half of the subrange contract.

The pre-fix contract stopped on the absent production helper at
`ledger/buildlogs/20260822T012738-837073.log`. The final device-free contract runs through
Blender's real `IndexBuf::init()`/`init_subrange()` for a rebased u16 child and a u32 child. Native
and Wasm require the exact plans `2 + 65536` and `12 + 0`; exact-source checks bind the helper to
both shipping draw arms and separately census EEVEE-shadow multi-viewport and mesh-subrange
producers.

## Evidence

- Canonical freeze and isolated replay: `ledger/buildlogs/20260822T013846-849701.log` and
  `ledger/buildlogs/20260822T014714-858706.log`. The 257-path / 20,258-entry patch is 1,541,575
  bytes at `sha256:6473b2a62a450260a41decd73fa200c3831c422763d9f8ac511cc0ad38108e8b`;
  live and replay manifests are byte-identical at
  `sha256:695321e772d5440ae3925eaa1cbec5962429649c3128f9aa7aedaeb92663a212`.
- Final root and descendant-CWD native/wasm32 contracts:
  `ledger/buildlogs/20260822T014644-857866.log` and
  `ledger/buildlogs/20260822T014655-858266.log`. Both emit identical 705-byte evidence at
  `sha256:c53cc5bcf105e0738670bccbe8dd26ccdcf38f30a5a003404f77d55768a945eb`, binding 23 source
  inputs at `sha256:2edcc824eca9e7b478e78aceddc688758178b24d663f4202b748749b6e5cd712`
  against Dawn `36cf1fae`, emcc 6.0.5, and Node 22.16.0.
- The real windowed product recompiled `wgpu_batch.cc`, linked `blender_browser.js`, and then
  reached exact locked-Ninja no-work: `ledger/buildlogs/20260822T014051-852482.log` and
  `ledger/buildlogs/20260822T014722-858846.log`.
- REUSE 6.2.0 is green for 2,020/2,020 files:
  `ledger/buildlogs/20260822T014728-858900.log`.

## Gate boundary

The required M3 scope remains red only for the absent fresh strict candidate
(`ledger/buildlogs/20260822T014311-854460.log`). Container-backed regression keeps M0 6/6 green
and M1-M8 red on their existing strict-receipt/APPLY/artifact/browser/run-label/hardware
boundaries (`ledger/buildlogs/20260822T014351-855124.log`). No instance, adapter, device, draw,
browser receipt, result promotion, dependency decision, deferral, tolerance, golden, blacklist,
or promise changed; s7 remains live.
