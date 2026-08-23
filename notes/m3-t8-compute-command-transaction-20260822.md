<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M3.T8 WebGPU compute command transaction - 2026-08-22

## Outcome

Patch 0209 makes direct and indirect compute dispatch fail closed when WebGPU returns a null
command encoder, compute-pass encoder, or finished command buffer. Neither path now performs
dependent pass work after a failed encoder/pass or submits a failed command buffer.

## Diagnosis and implementation

Both compute paths already validated dispatch geometry, shader modules, and pipelines, but they
immediately dereferenced `CreateCommandEncoder()` and `BeginComputePass()` results and submitted
the result of `Finish()` without validating any of those handles. A transient device-loss or
allocation failure could therefore become a null-handle call or an invalid queue submission.

The shared `command_pass_encode_submit_if_valid()` transaction validates the encoder, begins and
validates the pass, invokes the caller's pass body, ends the pass, validates the finished command
buffer, and submits exactly once. The same helper owns the complete sequence for direct and
indirect dispatch, leaving dispatch geometry and resource binding unchanged.

## Verification

- The unchanged source is rejected at the absent helper before evidence allocation
  (`20260822T235851-2089861`).
- Root and descendant-CWD native/wasm32 runs pass 18 byte-identical contracts at 1,773 bytes,
  SHA-256 `0f980496bd0627a8e3fedce03260f1cf560d84c9356d889d5945cea95fa029f7`, with the
  complete shipping input set at SHA-256
  `3b7d95dafae8afb19b76582aa50079674d75e9ba59ad08570a36402b8a4afdca`
  (`20260823T000138-2092142`, `20260823T000157-2093058`). The new four-case transaction proves
  encoder failure performs no pass work, pass failure performs no body/finish work, command-buffer
  failure performs no submission, and success begins, encodes, ends, finishes, and submits exactly
  once.
- Ambient Node 25.1.0 is rejected with an explicitly absent output directory
  (`20260823T000610-2098889`).
- The canonical freezer and replay retain 257 paths and 20,258 entries. The 1,655,648-byte patch
  is SHA-256 `e704474d063a60a6829de321e28fef22bd9969dc555ab42f337ce5727110e21b`; both
  manifests are SHA-256 `d5f7e5dc766fd360e7fe58d627d43a1d6a7226bf8851bf5da1a0e6b42ad72860`
  (`20260823T000101-2091600`, `20260823T000421-2097206`). Numbered patch 0209 is 100 lines,
  SHA-256 `c541060d41bb6a9265cbc83d80bbe1417cf53a862d6655610fb0865df4d768bf`, and
  reverse-applies cleanly to the live source.
- The real `blender_browser` rebuild and exact locked no-work check pass
  (`20260823T000238-2094659`, `20260823T000325-2095998`). OFF preflight binds the resulting
  118,072,764-byte primary Wasm (`20260823T000330-2096028`).
- Required M3 remains red for the absent fresh strict candidate
  (`20260823T000355-2096288`). Container-backed regression keeps M0 6/6 green while M1-M8 retain
  their existing strict-receipt, product, browser, run-label, and hardware boundaries
  (`20260823T000402-2096340`).

## Boundary

No WebGPU instance, adapter, device, pipeline, encoder, pass, dispatch, command buffer,
submission, pixel, or browser receipt is claimed. Live proof remains blocked by **no conformant
hardware Vulkan ICD in WSL2 (NVIDIA ships none; Mesa dzn rejected by Dawn)**. No result promotion,
dependency decision, deferral, tolerance, golden, blacklist, or milestone promise changed.
