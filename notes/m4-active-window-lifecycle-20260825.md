<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M4 active canvas window lifecycle — 2026-08-25

## Outcome

Commit `d343e9e` restores the `GHOST_WindowManager` ownership contract for the web canvas.
`createWindow()` now makes each successfully published canvas window active, and DOM focus/blur
transitions update the manager before their matching GHOST focus event. The separate live-canvas
pointer remains the event target while unfocused, so hover and owned drag delivery do not regress.

The predecessor real worker harness returned a null manager active window immediately after valid
window creation (`20260826T001607-67906`). The final WasmFS + `PROXY_TO_PTHREAD` run covers create,
blur, refocus, disposal, replacement, queued old listener epochs, bounded hit testing, and renewed
keyboard delivery (`20260826T001634-68172`). Focus and window-lifecycle source contracts reject 46
mutations, while the integrated native/wasm32 output remains byte-identical at 5,305 bytes,
SHA-256 `98f9c1ca84af8eff87f9bac77d839cb7305f95b34a718c5fdc8b50476deae8a1`
(`20260826T001726-68854`, `20260826T001735-68965`, `20260826T001743-69029`).

## Product and boundary

The optimized browser product recompiled both web GHOST translation units, relinked, and ended
locked-Ninja no-work (`20260826T001811-71258`, `20260826T001909-71839`). OFF preflight binds the
679,767-byte JavaScript, 119,034,129-byte Wasm, and 167,143,248-byte data artifact
(`20260826T001935-72195`). The intended canonical `/` entry reaches running Blender on the forced
fallback-software diagnostic, advances 78 idle ticks and nine trusted-input ticks with two new
presents, and reports zero stage-1/import/submission/transaction/device-loss failures
(`20260826T001950-72372`). This is diagnostic-nonreceipt evidence only.

Neighboring real-worker focus and canvas-keyboard checks pass, and headed WSLg Pointer Lock passes
pending/active/lost/error/blur/disposal (`20260826T002045-73869`, `20260826T002045-73870`,
`20260826T002316-76222`). A headless Pointer Lock rerun stopped at Playwright's third-click
actionability check because the page header intercepted the locator; it never reached a manager or
GHOST-state assertion and binds no evidence (`20260826T002158-75280`). Canonical replay and REUSE
2,596/2,596 remain green (`20260826T002446-79057`, `20260826T002725-81157`). Required M4 remains
red only at the existing unsupported hardware binding, and the container-backed regression restores
M0 6/6 while M1–M8 retain their strict boundaries.

No adapter, profile, split product, hardware receipt, result promotion, dependency, deferral,
tolerance, golden, blacklist, or promise changed. Mesa dzn and Windows were not attempted, WSL was
not restarted, and s7 remains externally blocked by `no conformant hardware Vulkan ICD in WSL2
(NVIDIA ships none; Mesa dzn rejected by Dawn)`.
