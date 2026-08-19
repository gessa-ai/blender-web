<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M6 render parity closeout

> **Artifact refresh required:** this receipt binds the three hashes below. The
> subsequent M5 click-pick relink changed the shipping JS/Wasm/data, so
> `ledger/results/m6.json` is intentionally RED until the full matrices are
> rerun and this binding is refreshed. The counts below remain historical
> evidence, not a claim about the newer bytes.

M6 is GREEN under the contract in `GOAL.md`: comparator passes plus explicit,
measured per-test SKIPs. No comparator threshold, golden, or failed row was
relabeled as PASS.

The executable source of truth is:

```sh
python3 sandbox/m6-prep/verify_render_closeout.py
harness/run.sh --scope m6
```

Both commands fail on artifact drift, missing evidence, stale blacklists,
unlisted pixel failures, GPU/page errors, non-physical render invocation, or a
changed pass/skip census.

## Current shipping binding

- JavaScript: `cd6b4798f5756c56a17e58d68062593f24433b279ae6fee7c9cd38dc69c5a306`
- Wasm: `0655c8843213cc1fe8590365c225a08faacb29f9b1b78def6879946f501d7fde`
- preload data: `06fa62fa70cb4b674189021d8985eccec0602c5c879b662f365716768bf1623d`

## Results

| Engine | Matrix | Pixel PASS | Justified SKIP | Functional/browser failures |
|---|---|---:|---:|---:|
| Workbench | `m6-current-wb-final-r2` | 19 | 1 | 0 |
| EEVEE | `eevee-final-full-r16` | 13 | 17 | 0 |
| Cycles CPU | `results-wasm-cycles.tsv` | 25 | 2 | 0 |

Workbench and EEVEE rows use one trusted physical F12 per case. The current
Cycles product smoke is `m6-current-cycles-f12-r5`; its pinned 64×64, 16-sample
factory-cube comparator passes and binds the same three shipping artifacts.

Every SKIP and its measured maximum/percentage is listed in
`sandbox/m6-prep/blacklist.txt`. Workbench's only remaining exclusion is the
single-pass AA edge resolve. EEVEE exclusions are feature-scoped ray payload,
transparency-dither, and Principled lobe/transmission fidelity gaps; the passing
controls include both colorspace rows, blended transparency, all four shadow
rows, ray attribute/direction, default/zero-coat/metallic/sheen. Cycles' two
exclusions are reproduced scalar-Wasm/native-SIMD numerical deltas.

These SKIPs are public renderer limitations, not hidden completion claims. A
future fix must first make the unchanged comparator pass; the verifier then
fails because the corresponding blacklist entry has become stale, forcing its
removal.
