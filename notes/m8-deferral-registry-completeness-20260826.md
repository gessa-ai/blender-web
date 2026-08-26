<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M8 launch deferral-registry completeness - 2026-08-26

## Outcome

The public deferral registry now names every launch-visible feature family that the shipping web
configuration explicitly compiles out. These are scope disclosures, not test waivers: no result,
tolerance, golden, blacklist, or receipt is changed. A chosen browser launch scope cut is a named
blocker; silence is not.

The same unit also narrows all six `wsl2-hardware-webgpu-*` rows to this host. A conformant,
driver-operated Apple M4 Pro exists, so the rows can no longer imply project-level impossibility or
point at the falsified Windows-reboot path.

## Forced-off coverage

| Registry id | Forced-off configuration | User-visible boundary |
|---|---|---|
| `feature-off-ik-solvers` | `WITH_IK_SOLVER`, `WITH_IK_ITASC` | Both armature IK solvers are absent; IK evaluation has no plugin callback. |
| `feature-off-bullet-physics` | `WITH_BULLET` | Rigid bodies do not simulate; Bullet-backed geometry paths are absent. |
| `feature-off-ocean-modifier` | `WITH_MOD_OCEANSIM`, `WITH_FFTW3` | Ocean simulation/modifier output is unavailable. |
| `feature-off-remesh-quadriflow` | `WITH_MOD_REMESH`, `WITH_QUADRIFLOW` | Remesh modifier and Quadriflow operator are unavailable. |
| `feature-off-exact-boolean` | `WITH_MANIFOLD`, `WITH_GMP` | Exact/Manifold boolean is absent; the fast float solver remains. |
| `feature-off-slim-uv` | `WITH_UV_SLIM` | Minimum Stretch unwrap falls back to conformal. |
| `feature-off-video-ffmpeg` | `WITH_CODEC_FFMPEG` | FFmpeg movie import/export and VSE movie paths are absent. |
| `feature-off-audio` | `WITH_AUDASPACE` plus codec/device backends | Playback, mixing, scrubbing, audio strips, and audio render are absent. |
| `feature-off-fbx-io` | `WITH_IO_FBX` | FBX import/export operators are absent. |
| `feature-off-alembic-io` | `WITH_ALEMBIC` | Alembic IO and cache evaluation are absent. |
| `feature-off-grease-pencil-vector-io` | `WITH_IO_GREASE_PENCIL`, `WITH_HARU`, `WITH_POTRACE` | Grease Pencil SVG/PDF vector IO is absent. |
| `feature-off-openimagedenoise` | `WITH_OPENIMAGEDENOISE` | OIDN/Cycles denoise is absent; the compositor node reports disabled and passes through. |
| `feature-off-freestyle` | `WITH_FREESTYLE` | Freestyle line rendering is absent. |
| `feature-off-motion-tracking` | `WITH_LIBMV` | Movie tracking, camera solve, and stabilization analysis are absent. |
| `feature-off-openxr` | `WITH_XR_OPENXR` | Native OpenXR/VR sessions are absent; no WebXR bridge exists. |
| `feature-off-jpeg2000-webp-dpx` | `WITH_IMAGE_OPENJPEG`, `WITH_IMAGE_WEBP`, `WITH_IMAGE_CINEON` | JPEG 2000, WebP, Cineon, and DPX IO is absent. |

`sandbox/m8-deferral-registry/verify.py` binds this mapping to
`patches/blender_web.cmake`, requires complete named rows, rejects duplicate IDs, and rejects stale
Windows-reboot or project-impossibility language in the six WSL-only hardware rows. Its self-check
mutates every required row and forced-off flag plus the host-scope language and requires each
mutation to fail closed.

## Hardware-receipt boundary

The exact WSL blocker remains unchanged: `no conformant hardware Vulkan ICD in WSL2 (NVIDIA ships
none; Mesa dzn rejected by Dawn)`. Software adapters continue to bind no profile, split product, or
receipt. The truthful revisit path is the driver-operated Apple hardware rig against an exact
artifact generation. The current CAPTURE split generation exists; accepted hardware profiles,
P0-D idle/stable viewport pixels, P0-E resize/recovery pixels, and a hash-bound APPLY relink remain
required before downstream hardware receipts can be claimed.
