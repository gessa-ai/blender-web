<!--
SPDX-FileCopyrightText: 2026 blender-web contributors
SPDX-License-Identifier: GPL-2.0-or-later
-->

# M3.T6 integrated buffer parity

This device-free contract compiles the canonical in-tree `wgpu_buffer` and
`wgpu_readback` postimages directly for native Dawn and WebAssembly. It checks
the exact buffer-usage matrix, alignment and index helpers, invalid-buffer
behavior, move lifetime, and the real readback registry's invalid-request
lifecycle, then requires byte-identical native/Node evidence.

Run it only through the build wrapper:

```text
harness/buildwrap.sh bash sandbox/wgpu-buffer-integrated-smoke/build.sh
```

The driver requests no instance, adapter, or device and creates no M3 receipt.
The historical live copy/readback cases remain part of `M3-LINUX-REPLAY` and
must not run against a software adapter.
