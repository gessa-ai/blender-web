<!-- SPDX-FileCopyrightText: 2026 Blender Web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# 0144 + 0146 accepted-baseline bookkeeping proposal

This directory contains a proposal only. Nothing here applies the patch, changes the live
ledger/dashboard, edits source, builds Blender, or stages files.

`accepted-baseline-reconcile.patch` has three deliberately narrow effects when an authorized
driver applies it:

1. append the already frozen patches 0144 and 0146 to `patches/series`, in that order;
2. replace the stale "0144 is next" M6 text with two checked targeted-unblock rows; and
3. append driver receipt rows for the accepted 0144 and 0146 evidence.

The accepted baseline represented by the proposal is:

| Receipt | GPUWebGPUTest census | Static shaders | EEVEE pixel claim |
| --- | ---: | ---: | --- |
| 0144 | 164 PASS / 7 FAIL / 2 CRASH / 173 | 970 / 987 | none |
| 0146 stacked on 0144 | 164 PASS / 7 FAIL / 2 CRASH / 173 | 971 / 987 | none |

The proposed rows record partial behavioral acceptance, not completion of M6.EEVEE-A or
M6.EEVEE-B. Both native and shipping wasm links completed. The 0144 browser control removed the
RG11 storage-error family but stopped on two later shadow shaders. The 0146 control removed the
tag-update writable-vertex error but retained the independent shadow image-atomic error. Both
controls had zero readback kicks, zero completions, and a black render-operator image.

## Explicit exclusions

The following are intentionally excluded and must not be folded into this proposal:

- Phase B1 shadow-atlas/image-atomic source WIP, including the now-live tri-state allocation
  path, its logs, and any prospective test count;
- L-B public async-readback work, including the now-static-accepted `GPU_readback.hh` API,
  readback implementation/tests, texture async API changes, and WebGPU texture changes;
- the combined B1 + L-B native link, targeted probe, interrupted wasm build, and all files under
  `sandbox/gpu-eevee-phase-b1/`;
- the WIP static result 973 / 989 and any WIP GPU census denominator at or above 174;
- L-C/F12 caller conversion, Film readback acceptance, browser matrix rows, pixel/golden claims,
  or M6 promise issuance;
- nonexistent 0145 or 0147 series entries; they remain mandatory future work, not patches;
- changes to upstream source, `ledger/deferred.json`, harness code, expected maps, thresholds,
  goldens, oracles, generated `ledger/results/*.json`, or `reports/dashboard.md`.

Generated M3 and dashboard files are not hand-edited by this proposal. After the bookkeeping
patch is authorized and the harness's separate accepted-baseline mapping is reconciled, the
authoritative rerun should report 164 / 173 for the GPU census and 971 / 987 static shaders.
Until that rerun, the current generated JSON/dashboard remain stale and must not be presented as
the accepted 0146 result.

## Live post-0146 inventory (not part of the patch)

This section records the newer live work without promoting it into the accepted 0144/0146
baseline. `accepted-baseline-reconcile.patch` remains unchanged.

| Slice | Honest current state | What is still required |
| --- | --- | --- |
| 0145 alias/cache coherence | `[ ]` mandatory; no frozen patch | incompatible same-byte aliases and shared-backing readback cache coherence |
| 0147 fidelity tail | `[ ]` mandatory; no frozen patch | plain-1D sRGB clear; plain-1D/3D mip generation; partial/offset and combined-aspect depth/stencil fallbacks; optional-RG11 render-target emulation; exact 1D-array `textureQueryLod`; guarded native `Float32Filterable` parity |
| B1 shadow atlas | `[~]` live tri-state/static partial | `ShadowAtlasStatus::{Ready,Pending,Failed}` and next-sync submission gating exist; native links and static shaders are 973/989, but shipping-wasm and browser Pending-to-Ready/Failed behavior, shadow mutation, Film readback, and pixels are not accepted |
| L-B public readback | `[~]` static ACCEPT only | owned `GPUReadback`, async texture entry point, consume/cancel/error surface, and native `texture_readback_owned_result` PASS exist; shipping-wasm link plus browser Pending-to-Ready, exact-byte, source-lifetime, consume-once, and cancellation evidence remain |
| L-C/F12 topology | `[~]` static ACCEPT only | the diagnostic WM-worker-to-WM-thread proxy/yield/resume/cancel shape exists; a live normal/cancel browser probe and replacement of the diagnostic delay with the real Film readback continuation remain |

The 973/989 result is not an accepted replacement for 971/987. It is a WIP static result: sixteen
static shaders still do not compile, and no shipping browser binary or pixel matrix receipt yet
backs the B1/L-B/topology stack.

### Exact substantive work remaining in the active closeout

Nine independently falsifiable slices remain. Seven directly gate the GOAL-defined M6 render
promise; 0145 and 0147 are mandatory ledger carry-forward for the entire goal, but become direct
M6 gates only if their paths surface in the pinned render matrix or the driver keeps the documented
pre-promise binding.

1. **B1 runtime acceptance:** finish the shipping wasm link, observe the shadow-atlas tri-state in
   the browser, reject allocation failure cleanly, and prove a representative shadowed scene over
   two frames plus a caster/light mutation with non-black unchanged-golden pixels.
2. **L-B runtime acceptance:** prove Pending-to-Ready exact bytes in bundled Chromium, retained
   source lifetime, undersized-consume retention, consume-once ownership, cancellation, and an
   explicit failed result on the shipping build.
3. **F12 topology runtime acceptance:** prove normal resume and pre-join/cancel/kill paths on the
   real WM worker without deadlock, use-after-free, stranded timer, or page/worker crash.
4. **Production L-C/F12 continuation:** replace the probe-only delay with the actual async Film
   readback state machine, resume the render job across event-loop turns, and publish a non-black
   RenderResult. Broader M5 caller conversion remains separate after the F12 slice.
5. **0145 ledger carry-forward:** implement and accept incompatible-alias plus shared-backing
   cache coherence.
6. **0147 ledger carry-forward:** implement and accept the six fidelity-tail families listed
   above.
7. **Workbench closure:** rerun the pinned 20-row suite and close or justify the eight accepted
   baseline failures: `aa-disabled`, `aa-single-pass`, `dof`, `in_front`, `in_front_dof`,
   `x-ray_1`, `acescg_blackbody`, and `rec2020_lights`. The two DoF rows previously carried GPU
   validation; the other six were pixel deltas without validation errors.
8. **EEVEE closure:** rerun all 30 pinned rows with real device bytes, then fix or justify every
   comparator failure. Current accepted pixel parity remains 0/30; static success is not a pixel
   result.
9. **Cycles disposition:** fix or explicitly justify the two remaining 25/27 residuals,
   `principled_bsdf_default` and `principled_bsdf_emission_alpha`, before the M6 receipt.

After the seven direct M6 slices, the non-substantive milestone closeout is: freeze/replay the new
patches, rerun the authoritative GPU/static/Workbench/EEVEE/Cycles gates, reconcile generated
results/dashboard, and issue the promise only if the pinned thresholds and justified-blacklist
rules pass. The entire-goal ledger remains open until 0145 and 0147 are also accepted or explicitly
rescheduled with evidence.

### Stale-marker census

For this census, a marker is a source-of-truth checkbox/status row, not every repeated number in a
generated mirror.

- **27 false-negative historical checkboxes in `fix_plan.md`:** 13 M1 rows (`M1.1`-`M1.9`,
  `M1.12`, `M1.15`, `M1.15b`, `M1.16`), 2 M2 rows (`M2.5b`, `M2.5`), 8 M3 rows (`M3.T4`,
  `M3.T4-T10`, `M3.F4`, `M3.F9`, `M3-hygiene`, `M3.F8`, `M3-GATE`, `M3-boundary`), and 4 M4
  rows (`M4.T11-old`, `M4.T15`, `M4.T16`, the superseded `M4.T23`). Their work is proven later
  in the same plan/progress ledger, but their unchecked/partial markers were never reconciled.
- **2 active M6 row bodies are stale, though their open markers remain honest:** `M6.EEVEE-A`
  still says 0144 is next, and `M6.EEVEE-B` does not record B0 plus the live B1 tri-state/static
  partial. The proposal corrects the 0144/0146 part only; B1 stays partial.
- **5 `ledger/deferred.json` entries need status/text reconciliation:**
  `node-ungroup-socket-flake` is resolved but retains a pending-hunt revisit;
  `feature-off-opensubdiv` and `feature-off-cycles-engine` contradict the accepted OpenSubdiv and
  Cycles-CPU builds; `storage-texture-atomics` needs a scoped B1-partial update rather than a pure
  post-launch premise; and `gpu-sync-readback-windowed` still says L-B must expose an API even
  though L-B is now static-accepted. None should be hand-edited before its owning evidence is
  packaged.

That is **34 stale source-of-truth status markers**: 27 historical checkboxes, 2 active-row
descriptions, and 5 deferred entries. Separately, **4 accepted bookkeeping rows are missing**
(two series entries and two progress receipts, all supplied by the proposal), and **2 generated
mirrors are stale as artifacts** (`ledger/results/m3.json` and `reports/dashboard.md`). The two
generated artifacts should be regenerated, not counted again as dozens of independent markers.

Run `bash sandbox/gpu-r61/ledger-reconcile/validate-proposal.sh` for read-only validation.
