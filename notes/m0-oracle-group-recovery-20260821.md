# M0 oracle process-group recovery — 2026-08-21

<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

## Outcome

The repository and Docker enrollment were already correct, but the autonomous loop's inherited
process did not include the account's `docker` supplementary group. Direct M0 execution therefore
reproduced the retired macOS-oracle fallback and passed only 3/6 checks. A group-scoped subprocess
using the account's existing non-interactive sudo policy reached the Docker daemon without changing
the account, socket, image, harness, or oracle.

The digest-pinned oracle verification passed through `harness/buildwrap.sh` at
`ledger/buildlogs/20260821T010835-2737827.log`. Running the protected harness through the committed
container shims then restored M0 to 6/6:

```bash
sudo -n -g docker scripts/oracle-container.sh with-env \
  bash harness/run.sh --scope m0
```

The required full regression was run through the same environment at `2026-08-21T01:09:16Z`.
M0 remained 6/6 GREEN. M1 through M8 remained honestly RED on their existing strict-manifest,
APPLY-artifact, browser-receipt, run-label, and hardware-adapter boundaries.

## Boundary

This is an inherited-process recovery, not a substitute for a fresh login in the migration
runbook. It creates no M0-M3 candidate manifest and changes no source, harness rule, oracle,
receipt, adapter profile, result expectation, deferral, tolerance, golden, or promise. The s7
hardware stop-condition remains live: llvmpipe binds no GPU or browser receipt.
