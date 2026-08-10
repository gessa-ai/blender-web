<!-- SPDX-License-Identifier: CC0-1.0 -->

# 0144 static freeze receipt

Date: 2026-08-09

Patch: `patches/0144-gpu-eevee-storage-format-and-final-mip.patch`

Patch SHA-256: `b4fdb24cb2c34740d2e60cff5dc9fcf33e8ac94d784f85f106ba2ae706f1d032`

Note SHA-256: `172aaa12b1bf14b62fda8f921d70701d3e41d651306a457ec047a8692ba0874c`

Probe plan SHA-256: `2158816899a96c303dcc5e38209ea6727d4e8eae83cb993de80ead0a5aef27fe`

## Applied 0144 source hashes

```text
f2185848a6ca23f171e84e12ef98f757c75449648fd6dbc4ba87c32bc0978896  source/blender/draw/CMakeLists.txt
37ac83800c8d2827a0104f31401ac8077432a03bb2fd6f59b0d54479693debe3  source/blender/draw/engines/eevee/eevee_depth_of_field.cc
0df778734fed9a2c6ea2c14364c1f0451cf58a3fa7f0a8f53f6cca81ba203c25  source/blender/draw/engines/eevee/eevee_pipeline.hh
5adf54a2072ea139c264f56a7ea2892b946747b6f2b98c34cdf9cf1c1f5a1c74  source/blender/draw/engines/eevee/eevee_raytrace.cc
488aabe4fb6d06306737b9e1f6a756b5682c6fb7907670d8137b98a9b56c7ba2  source/blender/draw/engines/eevee/eevee_storage_format.hh
6b230334af41019024efbd405cd98053ea9152ff5c1e309446bfe5d6a6a08824  source/blender/draw/engines/eevee/eevee_subsurface.cc
3b7e6b6342449d2e98c54f7b73e4e20ff7f034108e6c3c43bde159a267643714  source/blender/draw/engines/eevee/eevee_volume.cc
5a96abadda41993e4eec6978bc6ac918639df129debbeaabd1c38eca9363ad4e  source/blender/gpu/GPU_shader_builtin.hh
5e7bd8bfbf14b31b0e41fd2f2e1ce2073ff28931c540a2c5145cad0fc5590a64  source/blender/gpu/intern/gpu_shader_builtin.cc
ac5a4aecda91d259854294987b76bbedf6fbe43092e617ac0cff3d9b384377c5  source/blender/gpu/intern/gpu_texture_mipmap.cc
5c8bace09308a38bcb933a02c20f855c9da0166c6b80bed7738cb7e3380ee1b7  source/blender/gpu/shaders/gpu_shader_2D_update_mipmaps.bsl.hh
b498e611723399dd9719ae92fdf2c38b8e36e193b4ec88d0e72ff5d5020b8bda  source/blender/gpu/webgpu/wgpu_shader.cc
```

The original 11-path patch passed `git apply --check --reverse` against its applied state before
the shared source was restored. The updated 12-path patch includes the missing `bf_draw` header
manifest registration. It passed a read-only forward apply-check against the live restored baseline.
An isolated forward, reverse, and forward replay matched all 12 patched source paths exactly.

## Restored pre-0144 baseline hashes

```text
ca44ccf1c8473697e5e5ae361321ba45d4b4d572b609cbe17b8ddccfc15e3aef  source/blender/draw/CMakeLists.txt
112e33ed31ce7a46dbce111ba56d7fd69cfda7b8fde8d66aa2a3915cc02533ef  source/blender/draw/engines/eevee/eevee_depth_of_field.cc
f9c1da1f6bfc903e5ffe193a23217af2ea316d0ef35ca6a2165793fd9f9cb6d0  source/blender/draw/engines/eevee/eevee_pipeline.hh
51347ce914ac45ef6e107531d96800e800642b4de6c633a0207ebaa9583b222c  source/blender/draw/engines/eevee/eevee_raytrace.cc
271b2e61d29c2518c8ec144c50d15705f93edbb78fbe77d522b75624438fae89  source/blender/draw/engines/eevee/eevee_subsurface.cc
03f78fe721bdc4695986d78c1a2232ce510d7a84516fabb737cd56646910f1c7  source/blender/draw/engines/eevee/eevee_volume.cc
f9e994b96cf368504a47924f28bd0688cb7400068be6d9cde84ce110abdc3fcc  source/blender/gpu/GPU_shader_builtin.hh
0e9cda5c79e4e22e95ca0f35a9e185e39428569043606532f132fe6ed5545362  source/blender/gpu/intern/gpu_shader_builtin.cc
8305602d61b22a07da22025102f1101e9fed49a33dbdcaf7b4866afd3158618b  source/blender/gpu/intern/gpu_texture_mipmap.cc
45d57760c6bdc647f04eab1023157403ed4c966e2185bc84a8575b6d6aa72420  source/blender/gpu/shaders/gpu_shader_2D_update_mipmaps.bsl.hh
94774ab76db5880dfaf211d55b68cfae93036772a2764d9a1a46cc70b8b31c55  source/blender/gpu/webgpu/wgpu_shader.cc
```

`source/blender/draw/engines/eevee/eevee_storage_format.hh` is absent in the restored baseline, as
expected for a new 0144 file. All 0144 source remained unapplied in the live checkout at freeze
time. No build or browser run was performed during the freeze because 0138 acceptance required an
uncontaminated binary and 0143 remained an acceptance dependency.

## Post-freeze update, 2026-08-10

Patches 0138 and 0143 are accepted, and 0144 is now applied in the live stack. The patch bytes and
SHA-256 above are unchanged. Because 0143 changed disjoint regions of `wgpu_shader.cc`, the current
0144 preimage for that file is
`766cf94e1991fe49860a3dcc4d6136acb0277942f6f51813650616ef47807912` and the current 0144
postimage is `9a0aa786f23d97eab0289817282824c9cc99ff998c7177b7ee7b1b1c82182760`.
The other 11 0144 postimage hashes remain the values recorded above.

The freeze-time note and plan hashes above identify the historical preparation artifacts. Updated
note, plan, build, census, browser, and replay hashes are in `0144-final-receipt.txt` and
`0144-final-integrity.txt`.
