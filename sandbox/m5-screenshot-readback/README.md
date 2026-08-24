<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M5 screenshot async-readback contract

This device-free contract binds the stock screenshot operator to an owned window-capture request.
It requires exact byte-count validation, pending capture ownership across the file selector,
bounded modal polling after a direct or early-confirmed execution, one-shot consumption, matching
WebGPU row orientation, and cancellation before the retained offscreen is released. Native
backends retain immediate completion.

`run.sh` compiles Blender's real `gpu_readback.cc` with controlled requests in native and wasm32
configurations, compares their output byte-for-byte, validates the shipping source structure, and
requires canonical patch replay. It creates no WebGPU instance, adapter, browser receipt, profile,
or split product.
