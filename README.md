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

The public preferred-form source URL has not yet been supplied by the repository
owner. The static application deliberately shows that as an unresolved launch
blocker instead of linking to a placeholder or minified bundle. Before any public
launch, the owner must provide the real HTTPS repository URL so the application can
offer a one-click “Source code (GPL)” link.

Current conformance status is generated from on-disk receipts in
[reports/dashboard.md](reports/dashboard.md). A green subsystem result does not imply
the complete launch gate; `LAUNCH.md` and the fail-closed M8 verifier remain binding.
