<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M5 viewport colour readback contract

This device-free contract binds the View3D eyedropper's retained viewport copy to the public
owned-result readback API. It requires an exact kick/poll/consume lifecycle, no fallback to the
synchronous window sampler while the viewport request is pending, exact byte-size validation,
failure retirement, cancellation before texture release, and unchanged immediate completion on
native backends.

`run.sh` compiles Blender's real `gpu_readback.cc` with a controlled request in native and wasm32
configurations, compares their output byte-for-byte, validates the shipping source structure, and
requires canonical patch replay. It creates no WebGPU instance, adapter, browser receipt, profile,
or split product.
