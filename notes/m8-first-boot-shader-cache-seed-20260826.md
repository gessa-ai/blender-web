<!--
SPDX-FileCopyrightText: 2026 blender-web contributors
SPDX-License-Identifier: CC0-1.0
-->

# M8 first-boot shader-cache seed — 2026-08-26

## Outcome

The windowed CAPTURE product now includes a deterministic, read-only seed for the
first 100 WGSL translations used by a factory-startup boot. On the same rebuilt
binary and bundled Chromium software adapter, disabling that seed reaches the first
presentation in **22,472 ms**; enabling the bundled seed reaches it in **5,207 ms**.
The seeded run reports 101 cache hits, zero translation misses, and zero page errors.
This removes 17,265 ms from the measured cold path and crosses the 5–8 second local
diagnostic target.

This is deliberately a **software-adapter diagnostic, not a performance receipt**.
It binds no adapter, profile, tier result, hardware pixel claim, or launch promise.
The driver-operated Apple M4 Pro must measure the rebuilt product before any
hardware cold-start claim is made.

## Exact A/B evidence

Both final measurements used the product produced by the locked relink in
`ledger/buildlogs/20260826T221052-1316238.log`. The probe intercepts only the
environment assignment in `boot-windowed.js` for the disabled arm, setting
`BW_SHADER_CACHE_SEED=0`; the enabled arm serves the exact built files unchanged.

| arm | first presentation | cache hits | cache misses | page errors | log |
|---|---:|---:|---:|---:|---|
| seed disabled | 22,472 ms | 1 | 100 | 0 | `ledger/buildlogs/20260826T222012-1324056.log` |
| bundled seed | 5,207 ms | 101 | 0 | 0 | `ledger/buildlogs/20260826T222042-1324500.log` |

The exploratory extraction run took 22,591 ms cold and produced 100 entries;
pre-injecting those entries into an otherwise empty OPFS cache took 5,573 ms. That
predecessor experiment established the lever before the product was changed. The
checked-in probe is `sandbox/m8-shader-cache-seed/probe_seed.mjs`; all of its modes
print `BW_SHADER_CACHE_SEED_DIAGNOSTIC` and identify themselves as non-receipts.

## Product mechanism and fail-closed boundary

`scripts/build-shader-cache-seed.py` validates each extracted `.wgslc` cache envelope
and writes a sorted `BWSP` v1 pack. The product preloads that pack at
`/bw/shader-cache/first_boot.bwsp`. `WGPUShaderPersistentCache` still checks the
persistent OPFS cache first, then consults the immutable seed. Each seed record is
accepted only when its key, cache-format version, current toolchain salt, bounded
lengths, and payload checksum match the same contract as an OPFS entry.

Missing, stale, malformed, duplicate, or corrupt seed data is ignored per record (or
as a whole for an invalid pack); shaderc plus Tint remains the normal fallback. The
seed is read-only and never changes OPFS persistence semantics. Setting
`BW_SHADER_CACHE_SEED=0` supplies the exact-product diagnostic control.

Pack identity:

- entries: 100
- entry-envelope bytes: 1,492,338
- pack bytes: 1,494,350
- pack SHA-256: `7a2fba3f36da45a9bf42bbb614b85f5ec618aa619a9f97cfdc08ed3dd26b4a28`
- sorted input-entry-set SHA-256: `12218d2019256c9615e3af697d27d99567639ce7f47ac27a635d9fce26128376`
- cache salt hash: `c7b9302f88a06b25`
- extraction-generation `blender_browser.wasm.orig` SHA-256:
  `5a9d0944007313bed75ac3deaf24d3c48e443a423c93918dbb561abb76d0d65b`

The extraction-generation hash is provenance, not an acceptance shortcut: the final
same-binary enabled arm proves that every bundled record still matches the current
cache key and toolchain salt.

## Rebuilt CAPTURE product

The locked build and immediate locked no-work pass are green. Windowed preflight is
green in CAPTURE mode. Current product identities are:

| file | bytes | SHA-256 |
|---|---:|---|
| `blender_browser.js` | 707,278 | `54526da3f8a4ef180760c04c051528868b6761b9af466c528072c2a136fbeaab` |
| `blender_browser.wasm` | 120,497,886 | `6aca69e88048a678e78752eefea2e1ffe337d29beff2ae5a5a9b1d6187004d13` |
| `blender_browser.wasm.orig` | 119,144,751 | `b8b2a682ff09e5eb80ba125b3fb85cd4fe65193c3eabd577e8a794c9e6a9fda6` |
| `blender_browser.data` | 168,637,598 | `095d0ba748c3cdc2fcd0956def221e0f0d347d41d95e0a150a28670ab1cea24c` |
| `blender_browser.split-build.json` | 13,218 | `83ba0abdb135126d64fbe0f09faaa5e2cc5c357616af95b354d3c135f947f997` |

This relink changes `wasm.orig`, so the two accepted Apple profiles from the prior
CAPTURE generation cannot be reused for an APPLY build. Fresh accepted profiles must
be captured against `b8b2a682…` before the hash-bound APPLY relink.

## Payload accounting

The seed is highly compressible but not free. Pinned Brotli q11 compresses its
1,494,350 bytes to 87,696 bytes. The current staged dry run classifies the seed as
KEEP and reports 479 KEEP files / 14,487,620 raw bytes, 2,683,640 Brotli bytes for
stage-0 data, and 61,176 Brotli bytes for glue. Relative to the prior projection,
data plus glue increases by 88,944 bytes.

The last conservative complete-wire projection was 14,967,503 bytes. Before counting
the small compressed Wasm code delta, this change therefore projects to approximately
**15,056,447 bytes**, about **56.4 kB over** the decimal 15 MB launch bar. The cold
latency win does not excuse that regression. The next staged-payload cut must recover
at least 60 kB (and remeasure the entire current APPLY artifact) without removing
native-visible features.

## Verification

- deterministic seed contract: 100 records, six corrupt-pack mutations rejected
- numbered patch reverse application and canonical patch replay: green
- stage classifier and provenance self-checks: green; seed is explicitly KEEP
- source freeze and REUSE coverage: green
- exact rebuilt product A/B: 22,472 ms disabled vs 5,207 ms enabled, zero page errors

Open boundaries remain the fresh Apple hardware cold/pixel check, fresh hash-bound
CAPTURE profiles, APPLY relink and inventory verification, full current wire
measurement, P0-E resize recovery pixels, and P0-G widget-shadow pixels.
