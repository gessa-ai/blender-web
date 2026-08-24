<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# R8 GHOST callback controls

`run.sh` binds the covered R8 findings to the shipping
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
- all eight shipping callback roles must match an explicit method/callee/argument,
  capture-list, owner-gate, and callback-time device-state manifest; and
- one production-shaped role matrix must deliver all seven ordinary callbacks before
  fallback loss, then reject every retained callback after loss or owner destruction.

`callback_census.py` lexes C++ while discarding comments and treating literals as
opaque tokens, follows balanced call and lambda structure, and rejects owner-gate
captures outside that manifest. Its mutation controls require rejection of a
dead-text/alias false positive, an implicit outer capture, and an extra callback;
the first mutation deliberately preserves the retired grep gate's raw count of
seven. The driver also requires byte-identical native/wasm32 behavior under pinned
em++ 6.0.5 and Node 22.16.0. The deliberately unsafe check-then-use owner gate and
the in-place member ready callback reproduce their respective pre-fix heap use
after free under AddressSanitizer. The accepted paths must finish without an ASan
diagnostic or timeout.

Run only through the project build wrapper:

```sh
harness/buildwrap.sh sandbox/audit-r8/run.sh
```
