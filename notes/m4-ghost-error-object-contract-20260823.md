# GHOST present error-object contract — 2026-08-23

<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

## Outcome

Implementation commit: `ce5eb31`.

The browser compositor no longer treats a non-null WebGPU handle as proof of successful
creation or command validation. Backbuffer textures and the present pipeline remain private
candidates until validation, out-of-memory, and internal error scopes all complete cleanly.
Present command encoding completes under the same scopes before its command buffer can reach
`Queue::Submit`; submission then runs under a second scope. First-pixel logging and the keepalive
present counter advance only after that second scope succeeds.

This closes the GHOST half of audit R6's error-object finding. The GPU backend's null-only helpers
remain a separate highest-priority follow-up; no M3 claim is made here.

## Fail-first and contracts

The unchanged shipping call sites failed the new source-bound contract before evidence allocation
at `20260823T082202-2567279`: none used the scoped helper. Final root and descendant executions are
byte-identical at 2,698 bytes, SHA-256
`fe6ef3b06f3dacb2f3fe392415b4e14fe603f40307fead795912809e1073d171`, with combined shipping-source
SHA-256 `caee57cae9250ec571806554e3f8351234113b2ca42eb452aba47ccc4f8601b4`
(`20260823T083050-2575178` and `20260823T083104-2576013`). Their 18 GHOST cases cover:

- literal-null and non-null-error texture candidates, with no early extent publication;
- pipeline dependency failure, non-null error-scope rejection, and atomic pair publication;
- six literal command-handle failures, a non-null error command buffer rejected before submit,
  a submit-scope rejection, and one clean commit;
- no completion, publication, submission, or liveness mutation before the corresponding scope
  callback.

The exact pinned-Dawn software control rebuilt at `20260823T082715-2572515` and ran at
`20260823T082717-2572514`. LlvmPipe again proved all eight validation failures return non-null
objects, then the shipping helper passed four scoped rejected/accepted cases and kept the real
error command buffer out of `Queue::Submit`:

`DAWN_ERROR_HANDLE_AUDIT_PASS cases=8 null_guards_miss_validation=8 scoped_contract=4
error_object_submit_rejected=1 SOFTWARE_CONTROL_NON_RECEIPT`

This is API-semantics evidence only. The software adapter binds no GPU, browser, profile, split
product, pixel, or milestone receipt.

## Product and gates

The real `blender_browser` product rebuilt through the global Ninja lock in 37 seconds
(`20260823T082735-2573063`), then ended exact locked no-work and passed OFF-mode product preflight
(`20260823T082819-2573490` / `20260823T082819-2573489`). The required M4 scope remains honestly RED
at the unchanged unsupported historical binding (`20260823T083135-2576997`). Container-backed
regression restores M0 to 6/6 GREEN while M1-M8 retain their existing strict-receipt, split-product,
browser, run-label, hardware, and release boundaries (`20260823T083204-2577444`). The earlier
host-only aggregate at `20260823T083143-2577084` lacked the inherited Docker group and is
superseded.

No `upstream/`, harness, oracle, result expectation, receipt, profile, deferral, tolerance, golden,
blacklist, or dependency decision changed. The live pixel boundary remains blocked by
`no conformant hardware Vulkan ICD in WSL2 (NVIDIA ships none; Mesa dzn rejected by Dawn)`.
