<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# R8 GHOST callback controls

`run.sh` binds two R8 findings to the shipping
`platform_web/ghost/GHOST_WGPUTransaction.hh` helpers without creating a WebGPU
adapter or a milestone receipt:

- an imported browser loss must become terminal in every already-scheduled C++
  completion, without waiting for a later public owner poll;
- owner invalidation must exclude new delivery, wait for concurrent delivery, and
  remain reentrant when a completion destroys its own context.

The driver also binds all seven shipping completion sites to the synchronized
owner gate and requires byte-identical native/wasm32 results under pinned em++
6.0.5 and Node 22.16.0. The deliberately unsafe check-then-use owner gate
reproduces the pre-fix heap use after free under AddressSanitizer. The accepted
path must finish without an ASan diagnostic or timeout.

Run only through the project build wrapper:

```sh
harness/buildwrap.sh sandbox/audit-r8/run.sh
```
