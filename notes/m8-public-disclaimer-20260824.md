<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M8 public disclaimer closure - 2026-08-24

## Outcome

The standing non-affiliation statement is now complete in both the root README and the visible
browser shell: the text covers affiliation, endorsement, and sponsorship and retains the Blender
trademark statement. The preserved outer-worktree shell delta is integrated as one reviewed M8
unit, including its neutral title, local/offline proof, desktop limitation, legal-notice link, and
diagnostics-first script order. The staged browser verifier requires the same complete wording.

The current technical-compliance producer changes only `public_disclaimer_complete` from false to
true. Technical compliance remains green. Three external-policy facts remain honestly false:
OpenSubdiv compatibility judgment, a public preferred-form source URL, and coordinated history
repair.

## Evidence

- The restored pre-change source produced `public_disclaimer_complete=false` at
  `ledger/buildlogs/20260824T123147-26481.log`.
- Source commit `35736d9` adds the complete visible wording and a browser-free contract. The final
  focused run passes one live case and eight mutations at source SHA-256 prefix `b69cc929e08c`
  (`ledger/buildlogs/20260824T123543-29906.log`).
- Compliance producer `ledger/buildlogs/20260824T123543-29907.log` reports technical PASS with
  `public_disclaimer_complete=true`. The host-tool, runtime-consumer, receipt, staged-provenance,
  transport, JavaScript syntax, and REUSE checks are green at
  `ledger/buildlogs/20260824T123415-28284.log`, `20260824T123415-28288.log`,
  `20260824T123415-28295.log`, `20260824T123415-28306.log`,
  `20260824T123415-28312.log`, `20260824T123415-28320.log`, and
  `20260824T123543-29910.log`.
- The real `blender_browser` target is locked no-work and its development product passes exact OFF
  preflight (`ledger/buildlogs/20260824T123453-28707.log` and
  `ledger/buildlogs/20260824T123500-28777.log`).
- Container-backed regression keeps M0 at 6/6 green while M1-M8 retain their existing strict
  receipt, split-product, browser, hardware, and release boundaries
  (`ledger/buildlogs/20260824T123600-30164.log`).

## Boundary

This closes one public-policy source fact, not the launch gate. It creates no brand decision,
public repository URL, compatibility/legal judgment, history rewrite, deployment, browser run,
adapter, profile, split product, receipt promotion, deferral, tolerance, golden, blacklist, or
milestone promise. The live GPU/browser path remains blocked by no conformant hardware Vulkan ICD
in WSL2 (NVIDIA ships none; Mesa dzn rejected by Dawn); dzn and Windows were not attempted and WSL
was not restarted.
