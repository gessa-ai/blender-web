<!--
SPDX-FileCopyrightText: 2026 blender-web contributors
SPDX-License-Identifier: GPL-3.0-or-later
-->

# Local server entry-point contract

`selfcheck.py` starts `scripts/serve-web.sh` against temporary shell and binary
fixtures. It proves that a shell containing `windowed.html` serves that page at
`/`, that `BLENDER_WEB_ENTRY=index.html` preserves the legacy headless root, that
index-only custom harnesses remain compatible, and that an entry escaping the
shell directory fails closed. Every successful response also retains the
required COOP/COEP/CORP and no-cache headers.

Run from the repository root:

```sh
harness/buildwrap.sh python3 sandbox/serve-web-entrypoint/selfcheck.py
```
