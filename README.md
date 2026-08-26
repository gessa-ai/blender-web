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

## Release reproducibility

`scripts/package-tagged-release.py` produces the static-hosting archive and a
machine-readable sidecar receipt only from an annotated release tag at a clean
`HEAD`, a strict PASS `APPLY` split manifest, and the exact derived staged bundle.
It normalizes archive metadata and records every shipped byte, the source commit
and tree, the canonical upstream replay, the upstream pin, and the accepted
profile provenance. Run it twice with two fresh output paths and compare the
SHA-256 digests to require byte-identical archives:

```sh
bash sandbox/m8-staged-deploy/make_staged_bundle.sh
python3 scripts/package-tagged-release.py \
  --tag vX.Y.Z --output /tmp/blender-web-vX.Y.Z.tar.gz
```

Diagnostic `CAPTURE` generations are deliberately rejected and cannot be
packaged as releases. See [SETUP.md](SETUP.md) for build prerequisites.
