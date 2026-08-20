<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M8 staged-support Linux portability — 2026-08-20

## Outcome

The current staged assembly, exact-tree measurement server, and two-version
service-worker transition fixture now run their browser-free checks from the Linux
checkout root or a descendant working directory without reading an APPLY manifest.
The shell derives the repository from `BASH_SOURCE[0]`, Python from `__file__`, and
JavaScript from `import.meta.url`. The server imports the APPLY-specific aggregate
verifier only on its production path; its self-check exercises the same shipping-Wasm
source-copy seam with synthetic primary/deferred rows.

No bundle, APPLY artifact, browser process, GPU profile, or receipt was created. The
production path still requires the exact finalizer-owned split manifest and exact
public tree. Ornith-lab exposes only the rejected llvmpipe adapter, so the s7 hardware
blocker remains unchanged.

## Scope and invariants

- `make_staged_bundle.sh` retains the exact staged assembly and transport policy,
  confines replacement to a child of its derived generated-tree namespace, and adds a
  zero-write `--selfcheck` that reads no product input.
- `serve_measure.py --selfcheck` no longer calls `artifact_contract()`. A factored
  source-copy classifier accepts only basename-safe primary/deferred Wasm rows and
  rejects absent, escaped, transformed, or non-shipping fixtures. Production still
  loads and hash-binds the APPLY inventory before serving.
- `verify_update_transition.mjs` derives all source paths from its module URL and
  continues to model the same old-shell/new-register transaction, offline fallback,
  failed-claim retention, and corrupted-cache rejection.
- The current M8 runbook and migration table name the derived-root support checks and
  pinned CPython 3.13.13 / Node 22.16.0 commands.

No product/upstream source, service-worker transport rule, update-transition rule,
browser receipt, adapter identity, result flag, deferral, tolerance, golden, or promise
changed.

## Browser-free evidence

- Assembly self-checks pass from root and descendant CWD with six source seams,
  zero APPLY-manifest reads, and zero writes (`20260820T220021-2552867/2552881`). An
  explicitly absent product path also passes the self-check (`20260820T220215-2554455`),
  while an escaped output path is rejected before allocation
  (`20260820T220021-2552994`). The canonical bundle path remains absent
  (`20260820T220215-2554457`).
- Server root and descendant checks each pass the existing transport parser's 3
  positive / 11 negative fixtures plus 8 positive / 4 negative source-copy and Brotli
  checks, with zero manifest reads (`20260820T220021-2552833/2552834`).
- Update-transition root and descendant checks each pass 6 positive / 4 negative cases
  across two cache versions (`20260820T220021-2552842/2552849`). The three current
  support files contain no retired macOS root (`20260820T220215-2554456`).
- Bash, Python, Node, scoped-diff, and documentation checks are green
  (`20260820T220021-2552904/2552922/2552952/2552974`,
  `20260820T220157-2554269`). Independent M8 consumer, technical-receipt, and shared
  runtime-evidence self-checks remain green
  (`20260820T220157-2554257/2554258/2554262`).
- REUSE 6.2.0 is green for the complete checkout (`20260820T220337-2556444`).
- Required M8 remains honestly red on the same 43 receipt/APPLY/compliance prerequisites
  (`20260820T220438-2557317`). The final container-backed run restores M0 6/6 green
  (`20260820T220559-2559180`) and leaves M1-M8 red only on the existing strict
  receipt/artifact/split/hardware/run-label gates (`20260820T220605-2559883`). The first
  regression launcher inherited the pre-enrollment process group and was discarded after the
  Docker socket rejected it; the valid rerun used the account's already-enrolled `docker` GID.
