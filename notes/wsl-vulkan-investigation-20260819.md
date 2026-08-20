# WSL Vulkan hardware-adapter investigation — ornith-lab

<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

## Status

**BLOCKED before M4 replay.** The runbook requires a headed WSLg Chromium session with
a hardware WebGPU adapter. This machine exposes the RTX 4090 to CUDA and `/dev/dxg`,
but its Vulkan loader currently exposes only Mesa llvmpipe. A software adapter is not
an equivalent M4 receipt and must not be bound.

## Local evidence (2026-08-19)

- `nvidia-smi --query-gpu=name,driver_version --format=csv,noheader` reports
  `NVIDIA GeForce RTX 4090, 572.83`.
- `/dev/dxg` exists and is world-readable.
- WSLg is installed: `/mnt/wslg/runtime-dir/wayland-0` and
  `/mnt/wslg/.X11-unix/X0` exist. The onboarding shell did not export `DISPLAY` or
  `WAYLAND_DISPLAY`.
- `mesa-vulkan-drivers:amd64` is installed at `26.0.8-1ubuntu0.3`, but
  `/usr/share/vulkan/icd.d/` has no D3D12/dzn ICD JSON. Its listed ICDs are Asahi,
  gfxstream, Intel, lavapipe, Nouveau, Radeon, and virtio.
- `/usr/lib/x86_64-linux-gnu/dri/d3d12_dri.so` exists, but that is a Gallium driver,
  not a Vulkan ICD.
- `vulkaninfo --summary` reports exactly one physical device:
  `llvmpipe (LLVM 21.1.8, 256 bits)`, `PHYSICAL_DEVICE_TYPE_CPU`.
  The same result holds with the non-persistent WSLg environment
  `XDG_RUNTIME_DIR=/mnt/wslg/runtime-dir WAYLAND_DISPLAY=wayland-0 DISPLAY=:0`.

## Required resolution and acceptance

1. Restore/install a WSL-compatible hardware Vulkan ICD that enumerates the RTX through
   `/dev/dxg`; do not select llvmpipe or force a software backend.
2. Start the capture from a WSLg desktop session, exporting its actual display variables
   only for that session.
3. Re-run `vulkaninfo --summary` and retain output showing a discrete NVIDIA/D3D12-backed
   physical device rather than `PHYSICAL_DEVICE_TYPE_CPU`/llvmpipe.
4. Only then build/replay the M4 capture. The capture transcript must independently show
   Chromium WebGPU hardware-adapter selection before `bind_current.py` is permitted.

## Build status update (2026-08-20)

The earlier GitHub-mirror LFS failure was resolved by materializing the sources from the
canonical remote. The serialized s6 configure and Ninja build now pass. The current M4
product still has an independent fail-closed discrepancy: its required
`blender_browser.deferred.wasm` is absent. See
`notes/ornith-lab-s6-s7-20260820.md` for the exact artifact and m0 evidence. Neither
that discrepancy nor a successful rebuild relaxes the hardware-adapter requirement above.

## M3 probe portability update (2026-08-20)

Commit `68296ec` ports the bounded Dawn/Tint probe surface to Linux/Vulkan, removes the stale
macOS deployment cache key on Linux, and routes its build through the global Ninja lock. Both
probe targets compile against Dawn `36cf1fae`; the final locked dry-run reports no work. The T1
and T2 executables each identify llvmpipe as Vulkan adapter type CPU and exit 5 with
`PROBE_BLOCKED` before device validation. This is a successful fail-closed control, not an M3
receipt; the exact 197/1,003 replay remains pending a hardware adapter.

## Split-product correction (2026-08-20)

The missing `blender_browser.deferred.wasm` noted above is not an independent linker failure. The
reconstructed cache is in split mode OFF. The shipping shard can be created only after a CAPTURE
build produces a new Linux `.wasm.orig`, both strict browser profile scenarios pass on an accepted
hardware adapter, and that exact profile union drives APPLY. The software-adapter stop therefore
blocks the split profile as well as the M4 pixel receipt. The corrected cold-start sequence and
the fail-closed product preflight are in `notes/migration-to-ornith-lab.md` section 6/7 and
`scripts/windowed-product-preflight.py`.
