<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M5 image-paint depth continuation contract

This device-free Linux contract binds texture paint's inverted-clone cursor pick to the shared
owned progressive-depth request. It requires native-immediate behavior, latest-motion
supersession, no-hit preservation, producing viewport and cursor-snapshot guards, bounded timer
polling, exact release-event replay, cancellation cleanup, and unchanged non-clone painting.

`run.sh` reconstructs only the seven required canonical source paths in a temporary directory;
it never writes `upstream/`. It verifies patch 0261 in both directions, runs 16 fail-closed source
mutations, compares eight behavior contracts byte-for-byte on native clang++ 17 and wasm32 em++
6.0.5/Node 22.16.0, and compiles both exact patched production translation units with the locked
native and windowed-Wasm product commands. This is source/device-free evidence, not a hardware
WebGPU or live M5 receipt.
