<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M5 depth-eyedropper continuation contract

This device-free contract binds the stock depth eyedropper to the shared owned progressive-depth
request. It checks native-immediate and browser-pending accumulation, confirmation behind an
in-flight sample, newest drag-event supersession, reset/no-hit behavior, exact view-aligned depth,
and terminal drift/failure/timeout/cancel paths. The pinned direct-confirm behavior is retained;
normal mouse use begins sampling through `EYE_MODAL_SAMPLE_BEGIN`.

The source verifier rejects any synchronous GPU read from the eyedropper and binds the exact
producing window/screen/scene/area/region/view context. This is source and state-machine evidence,
not a browser, hardware-adapter, profile, split-product, or live M5 receipt. Navigation, painting,
zoom-border, and NDOF depth consumers plus the depth-cache and WM-capture families remain.
