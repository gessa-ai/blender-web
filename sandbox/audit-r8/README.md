<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# R8 GHOST callback controls

`run.sh` binds three R8 findings to the shipping
`platform_web/ghost/GHOST_WGPUTransaction.hh` helpers without creating a WebGPU
adapter or a milestone receipt:

- an imported browser loss must become terminal in every already-scheduled C++
  completion, without waiting for a later public owner poll;
- owner invalidation must exclude new delivery, wait for concurrent delivery, and
  remain reentrant when a completion destroys its own context.
- arbitrary-thread completions must serialize mutation of their shared GHOST owner,
  while nested delivery on the same thread remains reentrant.
- public owner execution and terminal cleanup must share that same reentrant slot;
- destruction must close admission before waiting, rejecting both nested and queued
  late delivery while an already-admitted callback drains.
- fallback device loss during backbuffer creation or surface configuration must clear
  pending initialization and invoke the failed ready settlement exactly once.
- the ready settlement must detach its callable from context member storage before
  delivery, so the callable can destroy that context and still finish safely.

The driver also binds all eight shipping completion sites to the synchronized,
serialized owner gate and requires byte-identical native/wasm32 results under
pinned em++ 6.0.5 and Node 22.16.0. The deliberately unsafe check-then-use owner
gate and the in-place member ready callback reproduce their respective pre-fix
heap use after free under AddressSanitizer. The accepted paths must finish without
an ASan diagnostic or timeout.

Run only through the project build wrapper:

```sh
harness/buildwrap.sh sandbox/audit-r8/run.sh
```
