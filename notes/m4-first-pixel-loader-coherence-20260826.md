<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M4 first-pixel loader coherence — 2026-08-26

## Outcome

The release loader no longer disappears on elapsed wall time before the canvas has presented.
`boot-windowed.js` keeps the existing `presentBackbuffer` stdout marker as its primary first-pixel
signal. If that marker's text drifts, a bounded fallback now polls the already-exported uncapped
`bw_present_count` and dismisses only after a finite positive count. The poll stops after 1,200
100 ms attempts and leaves the loader visible with one hidden diagnostic when no frame succeeds.
Gate mode remains unchanged.

This is shell-only. It does not alter or relink the CAPTURE Wasm generation; `.wasm.orig` remains
119,142,918 bytes at SHA-256
`5a9d0944007313bed75ac3deaf24d3c48e443a423c93918dbb561abb76d0d65b`.

## Behavioral evidence

The zero-input diagnostic uses the exact current CAPTURE binary with Chromium's software adapter,
so it binds no pixel, adapter, profile, or milestone receipt.

- The faithful legacy-timer mutation reaches `WM_main` at 1,044 ms, hides the loader at 3,556 ms
  with `presents=0`, and does not produce its first successful presentation until 22,194 ms. It
  therefore exposes 18,638 ms of black/shader warmup and then 16 recovery presentations
  (`20260826T214958-1298470`).
- Current source reaches `WM_main` at 985 ms and keeps the loader until the first successful
  presentation at 23,213 ms; hide and first-present timestamps are identical, `presents=1`, and
  there are zero page errors (`20260826T215042-1299006`).
- With the primary printf marker deliberately masked, the counter fallback observes the first
  present at 23,093 ms and hides 27 ms later with `presents=1`, proving format drift cannot restore
  zero-present dismissal (`20260826T215123-1299517`).

`sandbox/m4-frame-coherence/verify.py` binds the primary marker, the finite-positive counter test,
the 120-second bound, fail-closed timeout, one-shot scheduling, module-resolution arm, and gate
behavior; it rejects eight focused mutations (`20260826T214827-1296429`). The owner-specified
loader source/browser contracts remain green (`20260826T214827-1296430`,
`20260826T215259-1302403`).

## Public-bundle and release boundary

Public hardening/query behavior, monolithic/staged assembly, the pinned Terser minifier, disclaimer,
and deployment portability all remain green (`20260826T214827-1296434`,
`20260826T214827-1296441`, `20260826T214828-1296452`, `20260826T214828-1296461`,
`20260826T214828-1296467`, `20260826T214828-1296483`). Independent staged provenance records the
new deterministic four-program Brotli tuple as 24,719 raw-source bytes to 12,063 minified bytes,
saving 12,656 bytes (`20260826T214856-1297211`). This adds 181 bytes to the prior conservative
complete critical-wire projection, leaving it approximately 14,967,503 bytes, or 32,497 bytes
under the 15,000,000-byte ceiling; it is still not an APPLY or performance receipt.

Both source-freeze checks, technical-receipt self-checks, M8 consumer self-check, compliance tool,
and REUSE 6.2.0 are green (`20260826T215225-1300842`, `20260826T215225-1300844`,
`20260826T215225-1300843`, `20260826T215225-1300850`, `20260826T215225-1300862`,
`20260826T215225-1300871`).

The required M4 scope remains honestly red only at its existing unsupported browser-pixel binding
(`20260826T215450-1303877`). The authoritative pinned-container regression restores M0 to 6/6
green while M1-M8 retain their existing strict receipt, APPLY, browser, and parity boundaries
(`20260826T215615-1304690`).

The software adapter cannot show whether any transient-widget pixel flicker remains after P0-G.
That visual question stays in the driver's Apple P0-G/P0-E gauntlet. No hardware receipt, profile,
APPLY product, public bundle, result, promise, tolerance, golden, blacklist, or deferral changed.
