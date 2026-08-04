<!--
SPDX-FileCopyrightText: 2026 blender-web contributors
SPDX-License-Identifier: GPL-2.0-or-later
-->
# M3.T6.pre — WebGPU buffer wrapper (standalone-proven)

The common `GPUBuffer` wrapper the vertex/index/uniform/storage buffer classes
share. Drop-in for `source/blender/gpu/webgpu/wgpu_buffer.cc`.

- `wgpu_buffer.{hh,cc}` — usage-flag mapping from `GPUUsageType` + buffer kind
  (recon of the Vulkan backend's per-kind VkBufferUsageFlags), creation via
  `mappedAtCreation`, `update_sub` (queue.writeBuffer for ≤64 KiB — the analog of
  Blender's inline `vkCmdUpdateBuffer`, vk_buffer.cc:146 — else a staging buffer +
  CopyBufferToBuffer), and `read` via a MAP_READ staging buffer.
- `tests/wgpu_buffer_test.cc` — live Dawn/Metal harness: each kind create + upload
  + byte-exact readback + sub-range update, plus a >16 MiB staging-path buffer.

Build:  `harness/buildwrap.sh bash sandbox/wgpu-buffers/build.sh`
(Dawn-only; reuses build-dawn/dawn; build tree build-dawn/t6pre-build, gitignored.)

Findings: `notes/gpu-t6-t10pre-findings.md`.
