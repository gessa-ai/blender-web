<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M3.T3 native-context Linux preflight — 2026-08-21

## Outcome

The native GHOST WebGPU context had a post-migration source blocker independent
of s7: `GHOST_ContextWGPU::initializeDrawingContext()` selected Dawn Metal
unconditionally. Even a future accepted Linux Vulkan adapter could not satisfy
that request. Patch 0149 now selects the native Dawn backend by platform:
Metal on macOS, Vulkan on Linux, D3D12 on Windows, and no native backend for the
compiled-but-unused browser sibling.

The patch is verified without modifying `upstream/`. The T3 driver copies the
two exact current GHOST files into an isolated temporary tree, applies 0149,
and compiles that postimage against Blender's real GHOST headers inside Dawn's
pinned CMake target graph. Every build goes through `scripts/ninja-locked.sh`;
the old direct `clang++` plus Apple-framework link is retired.

## Fail-closed adapter boundary

Before constructing the GHOST context, the verifier performs the same exact
host-backend and hardware-adapter classification as the T1/T2 probes. Only an
integrated or discrete adapter on the selected backend can reach the T3 device
path. The current host reports Vulkan CPU adapter type 3,
`llvmpipe (LLVM 21.1.8, 256 bits)`, so both root and descendant-CWD runs emit
one `PROBE_BLOCKED` marker and allocate no receipt.

Pin validation precedes build-directory allocation. A wrong-Dawn control using
the Blender source repository as the candidate rejects commit
`fbe6228777e7d9afefcd61a413844e790ae75db7` before creating its requested
output directory.

## Evidence and boundary

- Retained pre-fix driver: `20260821T185622-464496`, fails because the old
  macOS-only direct compile expected an unavailable unversioned `clang++`.
- Patched postimage build: `20260821T190401-469899`, green.
- Root and descendant live controls: `20260821T190903-475288` and
  `20260821T190416-470236`, exact software rejection.
- Wrong-Dawn pre-allocation control: `20260821T190231-469150`, expected reject.
- Locked final dry-run: `20260821T190906-475443`, exact no-work.
- Canonical 257-path migration-snapshot replay: `20260821T190814-474937`, green.
- Exact REUSE 6.2.0: `20260821T190802-474502`, 1,950/1,950 green.

Patch 0149 initially remained a post-freeze source delta recorded in the
numbered development history. The next iteration composed its verified
postimage into the canonical migration snapshot using the source freezer rather
than hand-editing Blender source. The canonical patch is now 1,530,642 bytes,
SHA-256 `e03f140fe3f3c6448c9bc7bd52bfa572ea0f774fe5354cd98053341ef8d717b2`,
and still spans the exact same 257 paths and 20,258-entry source manifest. The
T3 verifier now reverse-checks 0149 as an integrated postimage before staging
and compiling those source bytes. Hardware context execution, the 197/1,003
suite, strict receipt, result promotion, and milestone promise remain blocked
by s7.
