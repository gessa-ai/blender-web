<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M7 branded-fallback contract self-check portability - 2026-08-20

## Outcome

The strict Firefox/Safari fallback producer and its aggregate M7 contract can now validate their
receipt, transcript, source-freeze, and Apple identity rules from Linux and from a descendant
working directory without an installed browser, WebDriver, or `codesign`. The production path is
unchanged in substance: it remains a two-row branded macOS capture, re-runs live Apple signature
checks, and rejects Linux before allocating an evidence label.

This is contract readiness only. No browser was launched, no fallback receipt was produced, and
no M7 result, schema, signing rule, adapter profile, deferral, or milestone promise was promoted.
The real browser matrix remains blocked by the s7 hardware/APPLY boundary on ornith-lab and by
the requirement to capture branded Safari on macOS.

## Reproduced defect

`capture_fallback.py --selfcheck` called `signed_driver_identity()` against the ignored
macOS-arm64 geckodriver path. On ornith-lab it stopped immediately because `codesign` does not
exist. `verify_m7.py --selfcheck` invokes that producer check, so the complete M7 contract
self-check failed at the same host-tool assumption before reaching its own adversarial fixtures.

## Repair

- Keep the default geckodriver path repository-derived and check its repository-relative identity
  in source instead of requiring the ignored binary during a browser-free self-check.
- Parse exactly one `Identifier=` and one `TeamIdentifier=` line. Wrong, missing, and duplicate
  values now fail closed; substring aliases are not accepted.
- Convert an unavailable identity executable into a concise `CaptureError` instead of an uncaught
  host exception.
- Exercise seven positive and ten negative host/signature/release fixtures without launching a
  browser. The aggregate verifier requires the exact self-check marker and fixture counts.
- Reject a non-Darwin production capture before source, server, browser, driver, or evidence work.
  This makes the portability boundary explicit without pretending Linux can supply branded
  Safari or treating Playwright WebKit as Safari.

## Evidence

- Original isolated failure: `ledger/buildlogs/20260820T200615-2449383.log` (`codesign` absent).
- Original aggregate failure: `ledger/buildlogs/20260820T200657-2449763.log`.
- Producer self-check, checkout root and descendant CWD:
  `ledger/buildlogs/20260820T201429-2454605.log` and
  `ledger/buildlogs/20260820T201429-2454608.log`.
- Aggregate M7 self-check, checkout root and descendant CWD:
  `ledger/buildlogs/20260820T201429-2454618.log` and
  `ledger/buildlogs/20260820T201429-2454630.log`.
- Linux production-host rejection occurs before label allocation:
  `ledger/buildlogs/20260820T201256-2454003.log`.
- Python syntax is green: `ledger/buildlogs/20260820T201429-2454604.log`.
- REUSE 6.2.0 is green: `ledger/buildlogs/20260820T201508-2455037.log`.
- Required M7 remains honestly red on the existing 34 missing staged/files/APPLY diagnostics:
  `ledger/buildlogs/20260820T201517-2455161.log`.
- Container-backed regression restores M0 6/6 green and leaves M1-M7 red only on the existing
  strict-manifest, browser-artifact, split-product, hardware, and run-label gates:
  `ledger/buildlogs/20260820T201641-2457289.log`.
