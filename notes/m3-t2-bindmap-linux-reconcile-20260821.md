<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M3.T2 binding-map Linux reconciliation — 2026-08-21

## Outcome

The device-free half of M3.T2 is reproducible on ornith-lab. Identical native
and Wasm executions use shaderc v2025.4 and Dawn/Tint `36cf1fae` to translate
the Blender-shaped two-stage shader pair. Both assert the complete default-Tint
renumbering and the normative reserved sampler map, then emit 6,911
byte-identical evidence bytes with
`sha256:26e1351ee71696fb84d02ae5eade2de0fbb585bbc3f7cbce7ff1761eaa036281`.

## Contract and implementation

`sandbox/wgpu-shader-wasm-smoke/bindmap_smoke.cc` compiles the established T2
vertex/fragment inputs to SPIR-V 1.3 and translates each stage twice. Its exact
resource census requires:

- default Tint: shared vertex `constants` remains at binding 5 while fragment
  `constants` moves to 7 and fragment material/storage resources move to 5/6;
- the complete explicit map `{0,1}->{0,257}, {0,2}->{0,258}`: both texture
  halves and every non-sampler retain Blender's dense binding, both sampler
  halves move to 257/258, and shared `constants` agrees at binding 5;
- exactly two vertex and eight fragment resource declarations in each mode,
  with no missing, duplicate, or extra declaration.

The existing parity driver now builds the new source natively through Dawn's
pinned Tint target graph and to Wasm through the checked four-entry shaderc and
63-entry Tint archive manifests. Both targets use `scripts/ninja-locked.sh`.
Success requires empty stderr, the exact semantic verdict, and complete output
byte parity. The original T1 output remains independently fixed at 498 bytes,
`sha256:2516371cb532`.

## Evidence and boundary

- Root run: `20260821T184431-453648`, both parity cases green.
- Descendant-CWD replay: `20260821T184537-455149`, all three locked Ninja invocations no-work.
- Wrong-Dawn negative: `20260821T184550-455540`, rejected before output allocation.
- Canonical 257-path source replay: `20260821T184640-455865`, green.
- Exact REUSE 6.2.0: `20260821T184855-458456`, 1,948/1,948 files licensed.
- Live control: `20260821T183937-451198` emits the exact T2 maps, then rejects
  llvmpipe with `PROBE_BLOCKED` before device/pipeline validation.
- Required M3 and group-scoped regression at 18:48Z remain honestly red only
  on the existing strict-receipt/APPLY/artifact/browser/hardware boundaries;
  M0 remains 6/6 green.

This work changes no product or upstream source, binding policy, adapter rule,
receipt, result flag, deferral, tolerance, golden, blacklist, or milestone
promise. Fresh C1 negative-pipeline rejection, C2 mapped-pipeline acceptance,
and the strict M3 receipt remain blocked by s7's hardware-adapter condition.
