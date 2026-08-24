<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M5 NDOF depth continuation contract

This device-free Linux contract binds the 3D View NDOF bounds fallback to one exact owned
rectangle-depth request. It requires bounds-first behavior, strict nearest-depth reduction,
native-immediate execution, exact owned motion payloads, FIFO replay across pending browser ticks,
producing-view guards, bounded polling, queue bounds, and convergent failure or cancellation.

`run.sh` verifies numbered patch 0263 and the canonical clean-pin replay, runs fail-closed source
mutations, compares eight behavior contracts byte-for-byte on native clang++ 17 and wasm32 em++
6.0.5/Node 22.16.0, and compiles the exact NDOF and navigation translation units in both
established build graphs with `WITH_INPUT_NDOF` enabled. This is source/device-free evidence, not
a hardware WebGPU or live M5 receipt.
