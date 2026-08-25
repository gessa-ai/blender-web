<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M4 web text clipboard — 2026-08-25

## Outcome

Commit `5d21f1c` replaces `GHOST_SystemWeb`'s null/no-op ordinary text clipboard with a
browser-main bridge that preserves GHOST's synchronous ownership contract across the
`PROXY_TO_PTHREAD` boundary.

A trusted DOM `paste` event copies `text/plain` into the main-realm cache before Emscripten's
queued WM-worker key callback is consumed. `getClipboard(false)` synchronously proxies to that
realm and returns a new null-terminated UTF-8 allocation from the Wasm allocator. `putClipboard`
synchronously converts Blender's borrowed pointer to an owned JavaScript string before starting
`navigator.clipboard.writeText`; promise rejection is contained and the in-app cache remains
usable. Permission-granted pointer interaction refreshes external text for menu-driven paste
without prompting ordinary clicks. Primary selection and image clipboard remain capability-off.
Diagnostics expose only source, status, sequence, and byte length, never copied text.

## Focused evidence

- The browser behavior probe proves trusted paste precedes simulated worker consumption and a
  later worker write reaches Chromium's system clipboard (`20260825T162955-1518865`). The old
  checked-in null/no-op methods reject under the final contract (`20260825T164201-1529580`).
- The final source verifier rejects 17 ownership, ordering, permission, selection, and privacy
  mutations. The broader native/wasm32 integration remains byte-identical at 5,139 bytes,
  SHA-256 `94588fb0021d722055e52e70594f869bb5f3a294afcf378aa843d059fc158ce5`, with source
  SHA-256 `35299b973dcce4bca34b388fc5365aa95abb4519b11ef25b1ded05d845217bb1`
  (`20260825T164343-1531307`).
- The real worker-topology GHOST harness covers external paste, system copy, Unicode/newlines,
  initial-null versus empty text, primary-selection rejection, and invalid operation rejection
  (`20260825T164320-1530913`, `20260825T164337-1531118`).

## Product and gate evidence

- Locked Ninja relinks the optimized browser product and then ends exact no-work
  (`20260825T164359-1532607`, `20260825T164447-1533041`). The baked-runtime contract binds
  671,088-byte JavaScript SHA-256 `595df7e066c839d2d9b1e87965235056e267128884a5a6f75971e3b119619618`,
  119,017,583-byte Wasm `fec45af475f5ff0158d073f368c45ca1d6efd826d0ba7d97940317b990886140`,
  and unchanged data `09e58a25849eb6290a181141f5f83f928f469fe1e4d9fbdba23210bcada5a351`
  (`20260825T164451-1533089`).
- In the real Blender product, Chromium system text pastes through GHOST into the Python Console;
  the executed expression sets `WindowManager.clipboard`, which travels back through GHOST and
  replaces the browser system clipboard. The run reports zero presentation rejections and zero
  device loss (`20260825T164459-1533175`).
- Required M4 remains red at the unchanged unsupported hardware binding
  (`20260825T164713-1535387`). Container-backed regression keeps M0 6/6 green while M1-M8 retain
  their existing strict receipt, split-product, browser, hardware, and release boundaries
  (`20260825T164720-1535506`). Final REUSE 6.2.0 covers 2,556/2,556 files
  (`20260825T164846-1537460`).

The product run uses Chromium's forced fallback software adapter and is diagnostic-nonreceipt
evidence. It binds no adapter, profile, split product, live receipt, result promotion, dependency
decision, deferral, tolerance, golden, blacklist, or promise. The named blocker remains
`no conformant hardware Vulkan ICD in WSL2 (NVIDIA ships none; Mesa dzn rejected by Dawn)`; dzn,
Windows Edge, and WSL restart were not attempted.
