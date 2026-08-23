<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M3.T10 vertex-buffer resource transaction - 2026-08-23

## Outcome

Patch 0226 (`9d8c391`) resolves every pipeline-planned real or dummy vertex-buffer handle into
an ordered temporary vector before direct batch, indirect batch, or immediate draw command
encoding begins. A missing handle rejects the complete binding plan without mutating the caller's
result, creating a command encoder, or silently omitting a slot that Dawn requires.

## Evidence

- The unchanged shipping source fails before compilation or evidence allocation at the missing
  fail-closed resolver (`20260823T052535-2409073`).
- Final root and descendant-CWD native/wasm32 runs pass 21 byte-identical integrated contracts at
  2,152 bytes, SHA-256 `89a7d11cb0dc1e460b9c7531a7e228a1c381e03fa1b190e8a3d6ecf162a9b8b3`.
  The 25 shipping inputs are SHA-256
  `0eab343e123399514b29d81839a382a1e31cb3690fed29ef30555823f7409f70`
  (`20260823T054003-2422772`, `20260823T054014-2423577`). Ambient Node 25.1.0 is rejected
  before its requested evidence directory exists (`20260823T053703-2418530`).
- The canonical freezer retains 257 paths and 20,258 live/replay entries. The 1,662,576-byte
  patch is SHA-256 `2294f2b213d45faf18f65e0615b67f6e71db337b43f44e08f4c7a9d1e715c254`,
  and both manifests are SHA-256
  `97af54a7a3f440afbd9f466287e1dd4945f79ec126383b9023c7c4553143a4b8`
  (`20260823T053226-2413086`). Canonical-only replay is green
  (`20260823T054454-2426831`). Numbered patch 0226 is 6,777 bytes at SHA-256
  `b4d4d717d6765996ee62dd0f2f4f0434aa7b70e368610353757bfd38c57e4f02`; isolated
  forward-check and live reverse-check are green (`20260823T054504-2426946`).
- The real `blender_browser` recompiles both draw implementations and relinks, then reaches exact
  locked-Ninja no-work (`20260823T053522-2417046`, `20260823T053617-2417553`,
  `20260823T054517-2427817`). OFF preflight binds the 118,079,151-byte primary Wasm at SHA-256
  `311e1acac63fa3c0f8dbe0a0e9f338109713b226bf8f36d5432fff1e5005a586`
  (`20260823T053623-2417602`).
- Final REUSE 6.2.0 is green for all 2,181 files (`20260823T054714-2428640`).
- Required M3 remains red only for the absent fresh strict candidate
  (`20260823T053812-2420380`). Container-backed regression preserves M0 6/6 green while M1-M8
  retain their existing strict-receipt, split-product, browser, run-label, hardware, and
  independent M8 performance boundaries (`20260823T053849-2420855`).

## Boundary

This is device-free resource-resolution proof. It creates no WebGPU instance, accepted adapter,
device, vertex buffer, command encoder, pass, draw, submission, pixel, browser receipt, profile,
or split product. Live proof remains blocked by **no conformant hardware Vulkan ICD in WSL2
(NVIDIA ships none; Mesa dzn rejected by Dawn)**. No result promotion, dependency decision,
deferral, tolerance, golden, blacklist, or milestone promise changed.
