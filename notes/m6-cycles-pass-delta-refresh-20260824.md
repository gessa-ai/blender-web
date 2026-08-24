<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M6 Cycles-CPU pass-delta Linux refresh - 2026-08-24

## Outcome

The hardware-independent Cycles-CPU matrix is freshly green against the current dedicated
Release Wasm product. Immutable receipt `m6-cycles-ornith-linux-20260824-r6` records 27 `PASS`,
zero `FAIL`, zero `SKIP`, zero stale exclusions, and zero blocked rows. Its receipt SHA-256 is
`4fd466beb9fb396ae81b5b30a9cfa253c7c18fc69551c3f35e8f6c7c6a2e469d`.

The current product binds JavaScript SHA-256 `f1028f32d168` (252,309 bytes) and Wasm SHA-256
`f1353a95e758` (134,479,653 bytes). The current Wasm differs from the August 20 r5 receipt, and
the unchanged verifier rejects r5 on that exact artifact-hash mismatch. The new r6 result table
has no verdict, maximum-error, or percent-over delta from r5 across any of the 27 scenes.

## Evidence

- Locked current-product rebuild: `20260824T124301-37617`.
- Final locked no-work proof: `20260824T124412-38531`.
- Shell/Python syntax and runner/verifier self-checks:
  `20260824T124428-38628`, `20260824T124428-38631`,
  `20260824T124428-38636`, and `20260824T124428-38644`.
- Old-receipt fail-closed control: `20260824T124428-38653`.
- Pinned-container producer: `20260824T124449-38807` (27 `PASS`, zero other verdicts,
  artifact stable).
- Independent pinned-OIIO live replay: `20260824T124722-48681`
  (`M6_CYCLES_CPU_PASS cycles=27pass/0skip`).

The schema-v3 receipt hash-binds the exact JS/Wasm pair, runner, render driver, staged add-on,
manifest, blacklist, result table, and every per-row input, golden, render, log, and comparator.
The independent verifier re-hashes that graph and reruns all 27 comparisons with the
network-disabled oracle image's pinned OIIO 2.4.17.0.

## Boundary

This is a fresh Linux M6 component receipt, not an aggregate M6 promotion. Workbench and EEVEE
still require truthful browser pixels from a conformant hardware adapter, and their named blocker
remains `no conformant hardware Vulkan ICD in WSL2 (NVIDIA ships none; Mesa dzn rejected by Dawn)`.
No GPU/browser receipt, result flag, deferral, tolerance, golden, blacklist, product profile, or
milestone promise changes here.
