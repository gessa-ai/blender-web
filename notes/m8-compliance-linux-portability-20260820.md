<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M8 technical-compliance Linux portability

## Outcome

The browser-free M8 technical-package compliance producer now runs reproducibly on the cold
ornith-lab checkout. It resolves only REUSE 6.2.0 from `BW_REUSE_BIN`, the documented
repository-local host-tool environment, or `PATH`; rejects missing, relative, empty, indirect,
non-executable, and version-drifted inputs before receipt allocation; and records the selected
executable's canonical path, size, and SHA-256 in the generated receipt.

The final pre-commit receipt passes all nine technical checks with REUSE 1,931/1,931. The four
external-policy facts remain honestly false: the public disclaimer is incomplete, OpenSubdiv's
TOST-1.0 compatibility awaits the required GPL-literate review, the owner has not supplied the
public source URL, and historical disclosure repair requires external mirror coordination.

## Failure and repair

The original Linux invocation failed before evidence allocation because `audit_compliance.py`
executed bare `reuse` and this reconstructed shell had no such `PATH` entry
(`ledger/buildlogs/20260820T221049-2565309.log`). The exact tool was previously available only
through an ephemeral `pipx run reuse==6.2.0` cache. The cold runbook now installs it into
`.host-tools/reuse-6.2.0`, and the producer binds the actual executable rather than relying on a
machine-global command alias. The host-only dependency decision is recorded in
`ledger/deps.json`; nothing from this Python environment is shipped in the browser product.

## Evidence

- Python syntax: `ledger/buildlogs/20260820T221642-2571036.log`.
- Resolver adversarial self-check: 3 positive / 7 negative, exact version 6.2.0
  (`ledger/buildlogs/20260820T221747-2573193.log`).
- Independent M8 runtime-consumer self-check remains green
  (`ledger/buildlogs/20260820T221642-2571037.log`).
- Real technical audit: `M8_TECHNICAL_COMPLIANCE_PASS`, all nine technical facts true,
  REUSE 1,931/1,931 (`ledger/buildlogs/20260820T221819-2573827.log`).
- Indirect-executable control rejected before writing evidence and left the current receipt at
  SHA-256 `60105c6c62c106ff5386e4d750acff000b928bae39a091363b4f6ff838d469f5`
  (`ledger/buildlogs/20260820T221834-2574274.log`).
- Required M8 scope moved from 43 to 22 technical failures: every compliance failure disappeared;
  the remaining failures are the absent APPLY/staged/browser/product receipts and M1-M7 aggregate
  rows (`ledger/buildlogs/20260820T221809-2573672.log`).

## Boundaries

No bundle, browser/GPU/APPLY receipt, result promotion, deferral, public-policy assertion, product
source, harness gate, tolerance, golden, or promise changed. M8 remains RED, and the s7
software-adapter stop condition still forbids CAPTURE/APPLY or any hardware-bound receipt.

## Audit correction

The subsequent 25-commit audit proved that the producer's recorded REUSE identity was not yet
consumed by `verify_m8.py`: a forged path/version/size/digest caused zero failures. Commit
`deac4ec` independently rechecks the exact live executable and adds a digest-tamper fixture.
The complete consumer self-check is green (`ledger/buildlogs/20260820T232148-2638488.log`);
the existing compliance receipt remains correctly stale until a complete current M8 candidate.
