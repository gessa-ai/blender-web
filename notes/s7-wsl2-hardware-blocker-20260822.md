<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# S7 WSL2 hardware-WebGPU external blocker - 2026-08-22

## Outcome

No conformant hardware WebGPU receipt can be produced inside this WSL2 instance. The exact
named blocker is:

> no conformant hardware Vulkan ICD in WSL2 (NVIDIA ships none; Mesa dzn rejected by Dawn)

This is a host receipt boundary, not permission to weaken a producer, reuse a historical
artifact, or accept a software adapter.

A software/fallback adapter binds no receipt, profile, or split product.

## Measured adapter boundary

Mesa 26.0.8 dzn is installed as an opt-in Vulkan-on-D3D12 ICD at
`/opt/mesa-dzn/share/vulkan/icd.d/dzn_icd.x86_64.json`. With its per-process environment,
`vulkaninfo --summary` exposes the NVIDIA GeForce RTX 4090 through Dozen as a discrete Vulkan
device. That hardware-backed Vulkan listing is necessary but not sufficient for the project.

The driver then ran the pinned `build-dawn/probe-build/dawn_probe` against dzn. Dawn rejected
the implementation before adapter acceptance:

```text
RequestAdapter failed: No supported adapters
no Vulkan adapter
```

The ordinary llvmpipe control instead reaches the probe's intentional `PROBE_BLOCKED` software
adapter stop. Headed Chromium likewise selects `vendor=google` / `arch=swiftshader`, not the
RTX 4090. Therefore dzn, llvmpipe, and SwiftShader all remain unable to authorize M3-M8 evidence.
The recorded dzn ICD and Dawn probe SHA-256 values on this host begin `6e5b149e8537` and
`7327473cf74d`, respectively.

## Why WSL cannot supply a different conformant NVIDIA path

The Windows driver store mounted read-only at `/usr/lib/wsl/drivers` contains the Windows
Vulkan loader `vulkan-1-x64.dll` (plus its x86 peer and Windows utilities). Its Linux shared
objects provide CUDA, NVML, encode, optical-flow, OptiX, NVVM, and DXG integration; there is no
Linux NVIDIA Vulkan ICD. NVIDIA does not publish one for WSL2. A different conformant
hardware-Vulkan implementation therefore cannot be selected from inside this VM.

## Tier disposition

- M1 and M2 are not deferred by s7; their fresh Linux CPU/runtime receipts remain the evidence.
- M3 needs a conformant native-Dawn adapter receipt.
- M4 and M5 need a hardware-backed shipping browser product for pixels and interaction.
- M6 Cycles-CPU remains 27/27 receipt-backed; only Workbench and EEVEE require the GPU receipt.
- M7's device-free and CPU IO work remains valid, but its strict shipping-product browser receipt
  requires the hardware-bound APPLY product.
- M8 still needs the hardware browser/product/soak matrix and independently remains blocked by
  the existing `m8-wasm-15mb-bar` size/latency failure.

The six exact dispositions live in `ledger/deferred.json`. They defer only evidence that cannot
truthfully be produced on this host; they do not turn a RED harness result green.

## Revisit path

A conformant path is staged for later through Windows-side Edge 150 over CDP. It requires a normal
host reboot before WSL interop and the recovery startup entry take effect. Fleet iterations must
never restart WSL to force that transition: doing so can strand the fleet and SSH access. After
the external reboot, execute `~/bw-logs/POST-REBOOT-WINDOWS-EDGE.md`, preserve every existing
adapter guard, and generate wholly fresh profiles and receipts.
