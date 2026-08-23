<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M3 GPU command error-object contract — 2026-08-23

## Outcome

Commit `d5029d5` closes the command/queue half of the R6 GPU error-object audit. Every short-lived
WebGPU command submission and direct `WriteBuffer`/`WriteTexture` call now passes through completed
validation, out-of-memory, and internal error scopes. A non-null Dawn error command is rejected
before submission, and a submission error is reported before the transaction can commit.

This does not close resource creation. Buffer, texture/view, sampler, bind-group/layout,
pipeline-layout, and pipeline candidates still need completed-scope publication and remain the
separate highest-priority `AUDIT-R6-GPU-RESOURCE-ERROR-OBJECT-CONTRACT` task.

## Implementation

`OrderedQueueScheduler` reserves a FIFO position before encoding begins. This is required in the
browser because `PopErrorScope` resolves only after control returns to the event loop: without the
reservation, a later direct queue write could overtake a delayed command submission and change
Blender's queue chronology. Encoding and finished-command validation settle first, then the
scheduler permits one submit under a second scope set. Failure poisons the current frame epoch and
cancels every later queued mutation from that epoch; `WGPUContext::begin_frame()` opens a clean
retry epoch.

Direct writes copy caller bytes into callback-owned storage. Command callbacks retain WebGPU
handles and heap-owned completion state rather than stack references. Native Dawn waits all three
scope futures; wasm uses spontaneous callbacks. Asynchronous texture/buffer readback starts mapping
only after a clean submission callback. The all-layer framebuffer load clear now changes
`CLEAR -> LOAD` from its completed clear callback, rather than from a synchronous handle-only
return.

Patch 0230 centralizes the shipping backend's only direct `Queue::Submit`, `WriteBuffer`, and
`WriteTexture` calls in those helpers. Source guards reject any bypass or reintroduction of the
old null-only command helpers.

## Evidence

- The unchanged source fails the new scheduler/helper source contract before build or evidence
  allocation (`20260823T085204-2591734`).
- The final root and descendant-CWD integrated runs compile the shipping source through locked
  native and wasm32 graphs and pass 25 byte-identical contracts. Evidence is 2,704 bytes at
  SHA-256 `2d3a9d43eec5d06cec488a691a9b1e9035ce2d984d190afc0852bbb9b24cf9aa`; the bound
  source hash is `56b3e6b47fea5be3113749982ade93e12ec810d0fca42bc2845c3852fe7a48b5`
  (`20260823T092734-2620504`, `20260823T092748-2621327`). The new six-case compute and buffer
  models cover three null handles, non-null encoding/submission error objects, clean acceptance,
  FIFO ordering, five same-epoch cancellations, and six next-epoch retries.
- The exact shipping helper compiles in the pinned Dawn graph (`20260823T092040-2612933`). Its live
  llvmpipe control reports `gpu_scoped_contract=2 gpu_error_object_submit_rejected=1` after one
  invalid non-null command and one clean retry (`20260823T092051-2613090`). The transcript says
  `SOFTWARE_CONTROL_NON_RECEIPT`; it binds no milestone or hardware claim.
- The canonical freezer proves a clean-pin patch regeneration and byte-identical 20,258-entry
  manifests (`20260823T092645-2619909`). The 1,699,119-byte canonical patch has SHA-256
  `957ec2c838c9ec63db074253962cc18045e5e0a695860cbc0d6c08d3b33c5438`; independent replay is
  green (`20260823T092954-2624022`). Numbered patch 0230 is 116,875 bytes at SHA-256
  `ea43324961c8ce8919f74abccb189c43e665092940ca784069bf69af283cff6e` and reverse-applies
  cleanly (`20260823T092954-2624023`).
- The real `blender_browser` recompiles the affected backend, relinks, then reaches exact locked
  no-work (`20260823T092803-2622147`, `20260823T092846-2622550`). OFF preflight binds the
  118,506,102-byte primary Wasm (`20260823T092909-2622778`).
- REUSE 6.2.0 reports all 2,195 files compliant (`20260823T093442-2627456`).
- Required M3 remains honestly red only for the absent fresh strict final candidate
  (`20260823T093250-2625996`). Container-backed regression keeps M0 6/6 green while M1-M8 retain
  their existing strict-receipt, browser, product, run-label, and hardware boundaries
  (`20260823T093318-2626323`). No gate result was promoted.

## Boundary

The live hardware WebGPU receipt remains deferred by the named blocker: no conformant hardware
Vulkan ICD in WSL2 (NVIDIA ships none; Mesa dzn rejected by Dawn). This iteration did not retry
dzn, launch a hardware browser, weaken a receipt, modify a result verdict, or claim live pixels.
