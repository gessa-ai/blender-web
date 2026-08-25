<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M5 interactive annotation depth-cache contract

This focused receipt binds `GPENCIL_OT_annotate`'s interactive draw completion,
polyline update, and depth-aware eraser paths to the owned full-viewport cache.
It checks native-immediate behavior, pending initial-event resumption, FIFO replay,
polyline cache refresh, exact timer/context guards, bounded queues/timeouts, and
failure/cancellation cleanup under native clang++ and wasm32.

The recorded-stroke `exec` callback deliberately retains Blender's synchronous
contract and remains named in `ledger/deferred.json`; this receipt creates no
adapter, browser profile, split product, or live M5 acceptance evidence.

Run through the canonical log wrapper:

```sh
harness/buildwrap.sh sandbox/m5-annotation-depth-cache/run.sh
```
