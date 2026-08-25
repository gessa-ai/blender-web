<!--
SPDX-FileCopyrightText: 2026 blender-web contributors
SPDX-License-Identifier: CC0-1.0
-->

# M5 curve-draw depth-cache continuation

This device-free contract covers both freehand curve draw operators. Surface projection must force
the stock depth pass without synchronously reading its full texture, then retain the exact starting
and subsequent custom-data-free events in a bounded FIFO until the owned full-viewport cache
settles. Native-ready requests stay immediate. Pointer or view drift, backend failure, timeout,
unsafe input, Escape, external cancellation, and queue overflow cancel the ticket, timer, and FIFO
without replaying stale input.

This closes the two curve-draw callers only. Other paint, annotation, placement, and particle-edit
depth-cache consumers remain, as does the separate WM window-capture family. Live M5 acceptance
remains hardware-blocked.

Run through the build wrapper:

```sh
harness/buildwrap.sh bash sandbox/m5-curve-depth-cache/run.sh
```
