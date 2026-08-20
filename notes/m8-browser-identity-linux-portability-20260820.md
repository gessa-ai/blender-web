<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M8 branded-browser identity portability - 2026-08-20

## Outcome

The current M8 Chrome + Edge matrix producer and its independent Python consumer can now validate
branded Linux packages without treating absent Apple signing fields as successful. The retained
Darwin path is unchanged in substance: canonical app member, exact vendor identifier/team/CDHash,
deep strict `codesign`, Gatekeeper acceptance, notarization origin, plist version, and terminal
byte-for-byte revalidation remain required.

The Linux receipt is a distinct schema-2 identity. It binds all of the following twice (producer
and independent verifier):

- the canonical non-symlink package ELF and its bytes/SHA-256;
- ELF64, little-endian, amd64, position-independent executable headers;
- exact `dpkg` ownership, installed version/architecture, and an empty `dpkg --verify` result;
- installed version equal to the APT candidate from the exact vendor URI;
- candidate package filename and SHA-256 from APT metadata;
- a dedicated one-line `arch=amd64 signed-by=...` source plus exact source/keyring bytes; and
- only the accepted vendor primary signing-key fingerprint in that dedicated keyring.

The runtime-reported version must equal both the Debian upstream package version and the current
platform-specific vendor stable API row. Chrome uses the `linux` Version History platform and
Edge filters the enterprise feed to `Linux`; the old MacOS selector is not reused.

This is producer and verifier readiness only. No Chrome or Edge package was installed, no browser
was launched, no browser matrix receipt was created, and no result flag, adapter profile,
deferral, or milestone promise was promoted. The live rows still require the s7-cleared hardware
WebGPU adapter and the exact APPLY split product.

## Identity authority

- Google documents active primary fingerprint
  `EB4C1BFD4F042F6DDDCCEC917721F63BD38B4796` and authenticated Linux package updates at
  `https://www.google.com/linuxrepositories/`.
- Microsoft documents its Linux repository signing keys and metadata-as-source-of-truth contract
  at `https://learn.microsoft.com/en-us/linux/packages`; the Edge repository continues to use the
  legacy Microsoft primary `BC528686B50D79E339D3721CEB3E94ADBE1229CF`.
- The exact dedicated source/keyring names and capture commands are frozen in
  `sandbox/m8-launch-gate/README.md` and mirrored independently in producer/verifier constants.

The required host-only GnuPG, GNU readelf/binutils, dpkg, and APT tools are recorded in
`ledger/deps.json`. They do not enter the browser runtime.

## Adversarial evidence

- Final shared identity self-check from the repository root: 25 negative cases covering both
  Darwin and Linux (`ledger/buildlogs/20260820T204918-2480247.log`).
- Final matrix producer self-check from root: 9 positive / 4 negative, exact Node 22.16.0,
  Playwright 1.61.1, and pngjs 7.0.0 (`ledger/buildlogs/20260820T204918-2480242.log`).
- Final independent Python consumer self-check: Linux verifier 3 positive / 5 negative plus the
  existing cross-lane identity/diagnostics contracts
  (`ledger/buildlogs/20260820T204918-2480243.log`).
- Descendant-CWD repetitions of producer, shared identity, and independent verifier:
  `ledger/buildlogs/20260820T203929-2472108.log`,
  `ledger/buildlogs/20260820T203929-2472131.log`, and
  `ledger/buildlogs/20260820T203929-2472091.log`.
- Real Linux production invocation with the canonical Chrome path fails before output allocation
  because the package is absent (`ledger/buildlogs/20260820T204011-2472395.log`).
- REUSE 6.2.0 is green (`ledger/buildlogs/20260820T204931-2480415.log`). The required M8 scope is
  honestly red for absent strict receipts/APPLY inventory
  (`ledger/buildlogs/20260820T204512-2475868.log`); container-backed regression keeps M0 6/6 green
  while M1-M8 remain red on the existing strict receipt, artifact, and hardware gates
  (`ledger/buildlogs/20260820T204631-2477811.log`).

Wrong ELF machine, package owner, APT candidate, signing fingerprint, package verification,
source options, host platform, runtime binding, and terminal receipt bytes each fail closed. The
self-checks launch zero browsers and make zero network requests.
