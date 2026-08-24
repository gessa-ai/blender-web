<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M5 zoom-border depth continuation contract

This device-free Linux contract binds the 3D View Zoom to Border operator to one exact owned
rectangle-depth request. It requires the stock post-clamp rectangle, strict nearest-depth
reduction, native-immediate execution, pending gesture-to-continuation handoff, exact zoom mode
and smooth duration, perspective/no-depth and orthographic fallback behavior, producing-view
guards, newest-request supersession, bounded polling, and convergent cancellation.

`run.sh` verifies numbered patch 0262 and the canonical clean-pin replay, runs fail-closed source
mutations, compares eight behavior contracts byte-for-byte on native clang++ 17 and wasm32 em++
6.0.5/Node 22.16.0, and compiles the exact production translation unit in both established build
graphs through the Ninja lock. This is source/device-free evidence, not a hardware WebGPU or live
M5 receipt.
