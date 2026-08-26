<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# Release metadata reconciliation - 2026-08-26

## Outcome

The five-file shipping metadata residue is now committed as `c5ad9ab`. The provenance map names
the implemented WebGPU/GHOST/shell/staging surfaces, the public third-party inventory reflects the
37 current Wasm dependency rows, the deferral ledger records the current resolved and deferred
feature boundaries, and REUSE covers the complete tracked checkout.

The stale OpenSubdiv description is corrected against the harvested bytes:
`lib/wasm/lib/libosdGPU.a` is a 200,032-byte archive containing `version.cpp.o` and
`glslPatchShaderSource.cpp.o`, and it exports the GLSL patch-basis source required by Blender's
WebGPU subdivision compiler. `libosdCPU.a` contains 49 objects. Neither archive is represented as
an empty compatibility placeholder.

Both custom-license runtime rows remain honest external-policy decisions. OpenSubdiv 3.7.0 and
OpenUSD 26.03 have exact license/notice payloads, but their TOST-1.0 compatibility/sufficiency is
recorded as unresolved until GPL-literate human review. Upstream inclusion is provenance, not a
project-side legal determination.

## Evidence

- Strict dependency inventory: `20260826T090415-609879`; schema-1 PASS, 37 dependencies, exact
  artifact inventory, external policy false for exactly `opensubdiv` and `openusd`.
- Dependency producer adversarial self-check: `20260826T090258-605322`.
- Launch deferral registry and WSL2 scope contracts: `20260826T090258-605321` and
  `20260826T090258-605325` (`features=16`, `flags=33`, `s7=6`).
- Compliance tool self-check and current technical producer: `20260826T090258-605334` and
  `20260826T090609-612566`; all nine technical package facts are true, while custom-license,
  source-URL, and history-policy decisions remain external.
- REUSE 3.3: `20260826T090415-609881`; 2,640/2,640 files carry copyright and licensing data.
- Authoritative pinned-container regression: `20260826T090601-611772`; M0 is 6/6 GREEN and M1-M8
  retain their existing strict receipt/product boundaries. The post-receipt M8 scope
  `20260826T090628-612565` reports the expected 23 APPLY/browser/product failures with no
  compliance-staleness failure.

## Boundaries

This work produces no new Wasm artifact, hardware profile, browser receipt, APPLY generation,
result promotion, tolerance, golden, blacklist, or milestone promise. The current CAPTURE product
still awaits accepted Apple success/terminal profiles after P0-E/P0-F verification. A public source
URL, product brand/trademark posture, both custom-license judgments, and the final hosting launch
remain human-owned decisions.
