<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# EEVEE B1 runtime marker contract

The browser gate is `drive_eevee_b1_two_frame.mjs`. It is sandbox-only and does not patch
production. Production markers are enabled only when `BW_EEVEE_B1_PROBE=1`.

Exact success grammar, independently within each physical-F12 console window:

```text
BW_EEVEE_B1 phase=ATLAS_STATUS status=PENDING requested=<u64> limit=<u64> forced=0
BW_EEVEE_B1 phase=ATLAS_STATUS status=READY requested=<u64> limit=<u64> forced=0
BW_EEVEE_B1 phase=RESOLVE_SUBMIT status=SUBMITTED loop=<u32>
```

One or more PENDING lines are allowed, but PENDING must be first, READY last, and at least one
resolve submission must follow READY. The driver attributes markers by the console-index interval
from one trusted F12 to that continuation's `BW_F12_ASYNC ... QUEUE_DESTROY`; marker output needs no
global render counter.

The ATLAS_STATUS marker belongs immediately after the image-render engine calls
`Instance::shadow_atlas_status()`. RESOLVE_SUBMIT belongs immediately after the WebGPU
`shadow_page_resolve_ps_` manager submission. `requested` is the actual allocation byte request;
`limit` is `GPU_max_storage_buffer_size()`.

Deterministic failure is a separate browser boot with both `BW_EEVEE_B1_PROBE=1` and
`BW_EEVEE_B1_FORCE_OVERSIZE=1`. The probe-only branch must make the local requested size exactly
`limit + sizeof(uint)` without changing the logical scene pool. Its exact marker grammar is:

```text
BW_EEVEE_B1 phase=ATLAS_STATUS status=FAILED requested=<limit+4> limit=<u64> forced=1
```

Failure acceptance requires requested > limit, no resolve marker, the normal attributed F12
failure/worker-return/queue-destroy topology, and no GPU validation error, page error, or crash.

Happy mode uses one boot and two trusted physical F12 events. After frame 1 is exported, its
passive timer applies `Cylinder.004.location.y += 0.35` and `Sun.rotation_euler.y += 0.25`. Frame 1
is compared to Blender's committed EEVEE reference. Frame 2 is compared to the pinned Blender
5.2.0 Metal oracle in `oracles/shadow_filter_b1_mutated_native_0001.png`. The two browser frames
must also differ beyond 4/255 for more than 8% of pixels.

Oracle provenance: Blender 5.2.0 LTS build `fbe6228777e7`, Metal backend, the upstream EEVEE test
setup script, input SHA-256 `07b15caaf1ea18bf6aa48d33dbb9ef987ac9217b794a083ef9ea4e03aaf6c1d8`,
and the fixed mutation above. The oracle PNG SHA-256 is
`4848b348b8a05e4c4e2e58c44cc5828e047e8ec71dd2ea8ec2c3b74b1e6440e1`. Two independent oracle
renders were comparator-identical at 4/255 and 0.08%; differing PNG hashes are metadata-only.

Commands after a shipping build and no-store server are ready:

```sh
NODE_PATH=/Users/paws/plushly/game-platform/node_modules node \
  sandbox/gpu-r61/f12-eevee-acceptance/drive_eevee_b1_two_frame.mjs \
  8151 300000 eevee-b1-r1 happy

NODE_PATH=/Users/paws/plushly/game-platform/node_modules node \
  sandbox/gpu-r61/f12-eevee-acceptance/drive_eevee_b1_two_frame.mjs \
  8151 300000 eevee-b1-force-r1 force-failure
```
