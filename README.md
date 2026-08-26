<!--
SPDX-FileCopyrightText: 2026 blender-web contributors
SPDX-License-Identifier: GPL-3.0-or-later
-->

# Source-derived WebAssembly editor port

This repository ports pinned Blender 5.2 LTS (`fbe6228777e7`) to a client-side
WebAssembly + WebGPU application. It is an independent derivative work and is not
affiliated with, endorsed by, or sponsored by the Blender Foundation. Blender® is a
registered trademark of the Blender Foundation and is used here only descriptively
to identify the upstream software from which this project is derived.

The aggregate project is GPL-3.0-or-later. Blender-derived files retain their true
upstream terms and attribution; see [LICENSE](LICENSE), [NOTICE](NOTICE),
[PROVENANCE.md](PROVENANCE.md), and [THIRD-PARTY.md](THIRD-PARTY.md).

Runs entirely on your device — WebAssembly + WebGPU. No server, no streaming.
After first load, disconnect your network and reload. Desktop only for this preview;
current Chrome or Edge is required.

The preferred-form source is this public repository:
[https://github.com/gessa-ai/blender-web](https://github.com/gessa-ai/blender-web).
The static application offers the same one-click “Source code (GPL)” link.

Current conformance status and the complete named limitation registry are published in
[PARITY.md](PARITY.md), generated from committed receipts and ledger data. A green
subsystem result does not imply the complete launch gate; `LAUNCH.md` and the
fail-closed M8 verifier remain binding.
