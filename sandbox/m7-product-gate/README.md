<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M7 strict product gate

`verify_m7.py` is fail-closed. A strict pass requires the exact current bundle,
`WITH_USD=ON`, immutable real browser and native OpenUSD receipts, the current staged
performance receipt at no more than **15,000,000 Brotli bytes**, and a branded Firefox
plus branded Safari fallback matrix.

The cross-browser producer must reserve
`fallback-evidence/<label>/receipt.json` without overwriting an existing path. Its immutable
per-label `fallback-evidence/<label>/selector.json` contains only the exact label, receipt
path, bytes, and SHA-256; no mutable global selector is accepted. Its consumable
contract is `fallback_receipt.schema.json` v4; each browser row includes a verified macOS
code-signing identifier/team and keeps input/download evidence under its labeled row
directory. Playwright WebKit is not Safari, and a
`renderer_unsupported` component probe is not a strict browser-row pass. Both rows must
boot the editor and prove a physical file chooser open, a completed real-browser download,
authoritative Blender-renderer pixels, and a clean nonce-bound OPFS semantic reload against
the exact browser-served bundle bytes. Safari uses a unique pre-proven-absent filename in
the canonical Downloads directory and moves only the completed exact file into evidence.

The production producer is `capture_fallback.py`. Run it only after the composite
two-root source freeze, while `sandbox/m8-staged-deploy/serve_measure.py` is serving
the exact canonical staged bundle. It uses W3C WebDriver against the canonical signed
Firefox and Safari applications; it never accepts Playwright Firefox or WebKit as a
branded substitute. The source-freeze receipt, producer bytes, automation-driver bytes,
and per-browser strictly ordered WebDriver transcript are hash-bound in receipt schema v4.
The same-origin `diagnostics-bootstrap.js` is loaded before every product script without
weakening CSP, and its early error/unhandled-rejection ledger must be exactly empty.
Evidence and its atomically published per-label selector are ignored post-freeze outputs.

Browser-free checks:

```
python3 sandbox/m7-product-gate/capture_fallback.py --selfcheck
python3 sandbox/m7-product-gate/verify_m7.py --selfcheck
```

These self-checks are checkout- and CWD-independent and do not require `codesign`, installed
browsers, or WebDriver binaries. They validate the exact macOS signing parser with positive and
adversarial fixtures. A production Firefox + Safari capture remains a macOS-only operation: the
real preflight still requires both canonical applications and re-runs `codesign` against every
app and driver before any evidence label is reserved.

Production capture (the exact-tree server must already be listening):

```
python3 sandbox/m7-product-gate/capture_fallback.py \
  --label "$RUN_LABEL" \
  --source-freeze "$FINAL_SOURCE_FREEZE/receipt.json" \
  --base http://127.0.0.1:8168 \
  --geckodriver "$PWD/.m8-browsers/geckodriver-v0.37.1-macos-aarch64/geckodriver"
```

The default Firefox driver is the locally ignored, release-pinned official Mozilla
`geckodriver` 0.37.1 arm64 binary under
`.m8-browsers/geckodriver-v0.37.1-macos-aarch64/`; its exact bytes,
version, Apple signature, launch command, process, session capabilities, and transcript are
verified. `--geckodriver` may name another location only when it has those exact frozen bytes.

The preflight fails closed if either canonical signed app, `geckodriver`, the system
`safaridriver`, the source freeze, or the exact-tree server is unavailable. A failed
label remains immutable with `INCOMPLETE`/`FAILED.txt`; its selector is never published.

Receipts are accepted by SHA-256 and byte length only. Filesystem modification times are
never freshness evidence.

Before running `verify_files.mjs`, derive its exact file allowlist from the finalizer-owned
split manifest via `verify_m8.bundle_files()` and write the generated, immutable
`bundle-identity.json`. The strict Python verifier independently loads that same M8 contract;
neither side guesses shard filenames.
