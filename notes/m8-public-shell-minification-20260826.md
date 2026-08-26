<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M8 deterministic public-shell minification — 2026-08-26

## Outcome

Commit `faff477` makes public-shell minification a deterministic, provenance-checked bundle
transformation. The public assembler now minifies four programs requested before semantic
interaction: `diagnostics-bootstrap.js`, `file-bridge.js`, the already fail-closed
`boot-windowed.js`, and `stage1-loader.js`. CAPTURE/APPLY Wasm, Emscripten glue, data payloads,
and reviewed development sources are unchanged.

The generated service worker and its registration control intentionally remain readable. Their
strict M8 consumer parses exact cache/version/update policy seams; retaining that audit surface
costs only the small residual outside the four dominant shell programs.

## Pinned tool and derivation contract

`public_shell_minify.mjs` resolves Terser only from the Emscripten 6.0.5 toolchain and fails unless
all of these identities match:

- Node `v22.16.0`;
- Terser `5.39.0`, BSD-2-Clause;
- package-lock integrity
  `sha512-LBAhFyLho16harJoWMg/nZsQYgTrg5jXOn2nCYjRUcZZEdE3qa2zb8QEDRUGVZBW4rlazf2fxkg8tztybTaqWw==`;
- executable `dist/bundle.min.js` SHA-256
  `ac4c20a115313612e52b93153165861ec710d2ec0329f27b968110d53df9c116`.

The options are fixed at two compression passes, identifier mangling without property mangling,
and SPDX-comment preservation. Output replacement is atomic and rejects non-regular input/output
paths. The dependency is recorded as a host-only build tool in `ledger/deps.json`; it is not
linked, preloaded, or shipped as a runtime library.

Independent stage provenance now regenerates every minified byte from the reviewed sources. It
also executes the minified Stage-1 loader through seven positive public/manual/stream/failure
cases, preserves the existing eight source-level mutation negatives, and binds the minifier plus
executable identity into the M8 proof. Release freezes and M7 fallback receipts include the new
producer source.

## Wire measurement

Pinned Node Brotli q11/lgwin-24 replay over the four actual public inputs, including the
fail-closed boot transformation, is now a permanent self-check:

| public programs | unminified | minified | saved |
|---|---:|---:|---:|
| diagnostics + file bridge + hardened boot + Stage-1 loader | 22,880 | 10,911 | 11,969 |

An exact synthetic split-bundle assembly measured the complete seven shell/control responses at
31,093 bytes before versus 19,120 after, a 11,973-byte reduction; the four-byte difference is
cache-version-dependent generated-control compression. The source-replay value above is the
conservative reproducible launch projection.

Applied to the post-StudioLight complete-wire estimate of 14,979,291 bytes, the conservative
projection becomes **14,967,322 bytes**, or **32,678 bytes under** LAUNCH.md's 15,000,000-byte
ceiling. This is a planning projection, not a receipt: accepted Apple profiles, the hash-bound
APPLY relink, exact public assembly, hardware pixels, and the <=8-second interaction measurement
do not yet exist for this generation.

## Verification and boundary

- The real production assembler completed against a synthetic, explicitly non-receipt split
  inventory, and independent full-stage provenance reproduced all raw and Brotli bytes
  (`ledger/buildlogs/20260826T171307-1046860.log`).
- Minifier, assembler, Stage-1/provenance, service-worker update, transport, M7/M8, both release
  freezes, final M0-M3/M0-M6 integration, generated-JavaScript syntax, and REUSE 6.2.0 self-checks
  are green (`ledger/buildlogs/20260826T173005-1060276.log`,
  `20260826T173005-1060277.log`, `20260826T173344-1068144.log`,
  `20260826T173519-1070511.log`, `20260826T173020-1060551.log`,
  `20260826T173502-1068856.log`, `20260826T172949-1058843.log`,
  `20260826T173502-1068850.log`, `20260826T173107-1061816.log`,
  `20260826T173502-1068849.log`, `20260826T173502-1068848.log`,
  `20260826T173143-1066429.log`, and `20260826T173519-1070493.log`).
- A headed fallback-adapter diagnostic boot of the minified controls reached `WM_main`, kept query
  hooks disabled, exposed empty early diagnostics plus both bridge contracts, and restored all
  2,963 Stage-1 files / 152,362,255 bytes with zero page errors. Its canvas remained black amid
  the existing fallback bind-group rejection storm, so it binds no pixel or hardware claim.

The CAPTURE `.wasm.orig` remains 119,142,918 bytes at SHA-256
`c9dbae361ec105441176124ce718b3227c1dcc17cee83742eb22254bfa67f962`. No build-tree artifact,
profile, APPLY product, public release bundle, hardware receipt, result promotion, tolerance,
golden, blacklist, deferral, or milestone promise changed. P0-E idle-resize pixels and the two
P0-F capture scenarios remain pending on the driver-operated Apple M4 Pro.
