<!--
SPDX-FileCopyrightText: 2026 blender-web contributors
SPDX-License-Identifier: CC0-1.0
-->

# M5 asset-preview window-capture continuation

This contract binds the `ASSET_OT_screenshot_preview` non-viewport capture path to the owned WM
window readback. The operator retains its exact crop, producing window/screen/main database, and
asset weak reference across an identified bounded timer. Native completion remains immediate;
browser completion resumes only after a later event-loop tick. Context drift, backend failure,
timeout, Escape, and external cancellation retire the request before operator state is freed.

The 3D-viewport render branch is unchanged. The synchronous Python `Window.screenshot()` method
also remains visible as the one separate WM-capture caller; this unit does not claim to solve or
defer that stock synchronous API.

Run through the build wrapper:

```sh
harness/buildwrap.sh bash sandbox/m5-asset-preview-window-capture/run.sh
```

