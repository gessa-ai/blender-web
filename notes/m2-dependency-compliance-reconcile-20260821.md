<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M2 dependency-compliance reconciliation

## Outcome

M2.8 is technically complete but cannot truthfully close its external-policy
condition. Fresh strict evidence covers the complete current dependency and
artifact inventory, while identifying one runtime dependency whose legal
compatibility remains explicitly unresolved: OpenSubdiv 3.7.0 under
`LicenseRef-OpenSubdiv-TOST-1.0`.

This iteration does not make a legal inference, relabel the custom text as
Apache-2.0, remove the launch-tier subdivision feature, or change any dependency
decision. The named prerequisite remains the GPL-literate lawyer review already
required by `notes/m8-technical-closeout.md`.

## Fresh evidence

- Run label: `m2-8-reconcile-20260821-r1`.
- Source freeze SHA-256: `c0b961e0498aa0d1c4068a71d7ccdd4902695a9f360123d13dbc9f9f5aa2734a`.
- Strict receipt SHA-256: `d2ddd151fb41156e6687adb0387e37d7ca9883938db8335bde9cdb90f453abe6`.
- Current ledger/spec: 37 exact matching `wasm_built` keys; 35 runtime-linked rows.
- Artifact inventory: 111 unique assigned paths, zero missing and zero unlisted.
- Technical verdict: schema-1 `PASS`, exact REUSE 6.2.0 green.
- External-policy verdict: `false`, exactly one unresolved row (`opensubdiv`).
- Runner adversarial self-check: schema-1 `PASS`, 23 positive and 192 negative fixtures.

The generated receipt is machine-local ignored evidence under
`sandbox/final-m0-m3/evidence/m2-8-reconcile-20260821-r1/`. Its durable technical
inputs are `ledger/deps.json` and
`sandbox/final-m0-m3/m2_dependency_inventory.json`; the strict producer is
`sandbox/final-m0-m3/run_m2_deps.py`.

## Disposition

Keep M2.8 partial/blocked in `fix_plan.md`. It may close only after the recorded
review resolves the custom-license compatibility/sufficiency question, or after
a separately verified faithful architecture removes or replaces that runtime
dependency. The current fidelity-first product keeps OpenSubdiv enabled.
