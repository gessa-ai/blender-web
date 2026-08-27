<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M8 current complete-wire projection — 2026-08-27

> Superseded for current planning by
> `notes/m8-pthread-shared-main-cache-20260827.md`. Commit `653ebe0` removes the duplicate worker
> source and measures 14,628,429 bytes of hybrid complete critical wire, 371,571 bytes under the
> decimal ceiling. The evidence below remains the exact pre-change baseline.

## Outcome

The canonical public assembler and its independent full-stage provenance replay now close the
remaining generated-control uncertainty around the current CAPTURE shell and Stage-0 payload.
Every contract-mandatory critical response was regenerated with pinned Node 22.16.0 Brotli
q11/lgwin-24, including content-bound service-worker controls.

The result is deliberately a **cross-generation hybrid planning fixture**, not a shipping bundle:
it combines the earlier c9 provisional primary with the current b8 shell/data/control tree. The
fixture lives outside the build tree, carries `shipping_authorized=false` and
`receipt_authorized=false`, and does not authorize APPLY.

| component | Brotli bytes | authority |
|---|---:|---|
| earlier c9 provisional primary Wasm | 12,292,157 | shape-only; produced from the earlier r1 profile union |
| exact current Stage-0 data | 2,230,167 | current b8 source, canonical packer |
| exact current page glue | 61,066 | current b8 source |
| exact current pthread worker source | 61,066 | byte-identical to page glue |
| all other current critical shell/font/generated controls | 44,825 | current b8 source and generated cache tree |
| **hybrid complete critical wire** | **14,689,281** | **planning only** |

The exact current non-Wasm/control subtotal is **2,397,124 bytes**. Therefore a real current
profile-split primary must be at most **12,602,876 bytes** to meet the decimal 15,000,000-byte bar.
The hybrid primary leaves 310,719 bytes of provisional margin. This replaces the earlier
14,678,797-byte lower bound and closes its 10,484-byte generated-control delta.

## Why the current primary was not guessed

The accepted Apple r2 profiles are valid for their c9 generation and contain 136,751 counters;
their success/terminal union marks 20,447 functions hot. The current
`b8b2a682ff09e5eb80ba125b3fb85cd4fe65193c3eabd577e8a794c9e6a9fda6` original contains
136,754 defined functions. Protected controller ordinals also move by four across the generations,
so the difference is not an append-only three-counter change.

Binaryen's checksum guard rejects the old profile first. Rewriting only that checksum would still
fail on the counter count; padding or shifting counters without an exact function map would attach
hotness to the wrong bodies. The experiment stopped at that boundary. Fresh accepted success and
terminal-error profiles from the driver-operated Apple rig are required to determine the real
current primary and authorize APPLY.

## Evidence and boundary

- accepted-profile merge and current structural rejection:
  `ledger/buildlogs/20260827T015713-1503021.log`,
  `ledger/buildlogs/20260827T015713-1503039.log`, and
  `ledger/buildlogs/20260827T015734-1503182.log`;
- explicitly nonreceipt hybrid fixture identities:
  `ledger/buildlogs/20260827T020614-1509178.log`;
- canonical full-tree assembly and contract-defined byte inventory:
  `ledger/buildlogs/20260827T020626-1509258.log` and
  `ledger/buildlogs/20260827T021226-1513278.log`;
- independent Stage-0 derivation, generated-control, and Brotli replay:
  `ledger/buildlogs/20260827T021254-1513444.log`.

No build-tree artifact, profile, APPLY shard, public bundle, hardware receipt, milestone result,
tolerance, golden, blacklist, deferral status, or launch claim changed. M8 remains partial/red until
the exact current APPLY bundle passes complete critical wire <=15,000,000 bytes and decoded semantic
interaction <=8 seconds on conformant hardware.
