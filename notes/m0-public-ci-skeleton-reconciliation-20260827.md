<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M0 public CI skeleton reconciliation — 2026-08-27

## Outcome

M0.9 is source-complete. The original deferral said to revisit the CI skeleton after a GitHub
repository existed. The owner has now supplied the public preferred-source destination, while the
canonical tree already contains `.github/workflows/m0.yml` and its executable payload at
`scripts/ci/m0-basic.sh`.

The workflow is deliberately an M0 skeleton, not a hosted milestone runner. It has read-only
repository permissions, full-commit pins for checkout, cache, and REUSE actions, exact emsdk and
Emscripten identities, and separate persistent Emscripten-system and compiler-object caches. It
does not write a project receipt or infer a milestone result.

## Executable verification

The exact workflow payload was run through `harness/buildwrap.sh` with the workflow's cache
locations and `M0_VERIFY_UPSTREAM_FETCH=1`. It passed all of the following:

- emsdk repository commit `1ab2e627b1a84567f5284d1baaa5f6be7ccf07de`;
- Emscripten 6.0.5 release commit `dbd755b5da399329c2576f6e3dfa7f419f5d8409`;
- emcc commit `1db513782be24469589d7cb8a1f1834e9a33f271` and bundled Node 22.16.0;
- repeated `ccache emcc` compilation with at least one measured cache hit;
- hello-Wasm execution under the pinned Node runtime;
- an emdawnwebgpu-port compile; and
- shallow fetch and exact identity check of Blender commit
  `fbe6228777e7d9afefcd61a413844e790ae75db7`.

The independent M0 structural self-check also passed, binding the workflow action pins, cache
variables, executable entry point, protected source pin, oracle container shape, and shell syntax.

Evidence:

- `ledger/buildlogs/20260827T034832-1582162.log` — structural self-check;
- `ledger/buildlogs/20260827T034832-1582163.log` — executable CI payload.

## Hosted boundary

An unauthenticated GitHub workflow/API probe returned HTTP 404 from this host. That does not
authorize an inference about a hosted run, repository visibility, or Actions state. M0.9 therefore
claims only the locally reproducible CI skeleton required by GOAL.md. Publication and observation
of a hosted run remain owner/driver operations; no remote, credential, receipt, result flag, or
milestone promise changed here.
