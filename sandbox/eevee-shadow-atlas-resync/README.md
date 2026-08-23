<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# EEVEE shadow-atlas READY-to-sync contract

`test_contract.py` binds the resumable image-render transition to the production
Phase-B shadow-atlas state. A WebGPU atlas can settle after `Instance::init()` has
already built passes without its SSBO. The READY arm must therefore rebuild those
passes exactly once before advancing to sample rendering.

Run from any directory:

```sh
.host-tools/bin/python3.13 sandbox/eevee-shadow-atlas-resync/test_contract.py
```

This is device-free structural evidence. It creates no adapter, pixel, profile,
receipt, result promotion, or M6 claim.
