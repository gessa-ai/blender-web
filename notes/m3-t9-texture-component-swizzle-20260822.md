# M3.T9 sampled texture component swizzle parity - 2026-08-22

<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

## Outcome

Patch 0171 closes a sampled-texture parity hole in the registered WebGPU backend.
`WGPUTexture::swizzle_set` retained Blender's four-byte channel mask, but `sampled_view()` ignored
it and always created an identity view. Real launch-tier callers rely on non-identity masks,
including EEVEE's `rgrg` velocity view and the paint cursor's `rrrr` mask view.

Sampled views now translate Blender's documented `rgba` / `xyzw` / `01` alphabet to Dawn's stable
`TextureComponentSwizzleDescriptor`. Identity masks need no feature and preserve the ordinary view
path. A non-identity mask is chained only when the active device exposes
`TextureComponentSwizzle`; invalid bytes or an unavailable feature return a null view rather than
silently sampling the wrong channels. Storage views, attachments, copies, and readback keep the
backing-channel identity because the descriptor is confined to `sampled_view()`.

Native GHOST device creation requests `TextureComponentSwizzle` only when the selected adapter
advertises it. The browser preinitializer already copies every exposed adapter feature into the
device request, so the browser and native paths use the same capability boundary.

## Device-free contract and integration

The expanded texture contract first failed against the unchanged source because the translation,
view-chain, feature, and launch-tier caller wiring was absent
(`ledger/buildlogs/20260822T073923-1168743.log`). The optional-feature extractor independently
failed before the native request existed (`ledger/buildlogs/20260822T073923-1168744.log`).

The final root and descendant texture runs are green
(`ledger/buildlogs/20260822T075019-1178093.log` and
`ledger/buildlogs/20260822T075030-1178504.log`). Native and Node 22.16.0 emit the same 937 bytes at
SHA-256 `a8122b075ceda916b2f10774a50173999705530951b5478ee51f8e3a2e1242a5` and bind eighteen exact
upstream source inputs at SHA-256
`6ef71a46086a7590b2a294a1d4088d8f618ff9986b66529e41678903ed60675b` against Dawn
`36cf1fae0cd8a81a4fb4580751648b80b2e6255c`, emcc 6.0.5, and Node 22.16.0. Eleven contracts now
include all ten valid swizzle symbols, four alias pairs, both constants, invalid-byte rejection,
exact sampled-view chaining, native feature opt-in, browser feature forwarding, and representative
EEVEE and paint-cursor callers.

The native GHOST build contract passes all 512 combinations of its nine optional features, with
`Float32Filterable` at index 2 and `TextureComponentSwizzle` at index 3. Root and descendant
build-only runs are green (`ledger/buildlogs/20260822T074314-1171846.log` and
`ledger/buildlogs/20260822T075046-1179742.log`); the llvmpipe software-blocked control remains green
and emits no hardware receipt (`ledger/buildlogs/20260822T074511-1174103.log`).

The final-source freezer retains 257 paths and 20,258 manifest entries. Its 1,563,091-byte
canonical patch is SHA-256
`e8ef2bc5549b8d81b1bb000b54a9ad680714d09c0fe01ee5e217088b46aa6183`, with byte-identical
live/replay manifests at SHA-256
`4a20cb6de8562ef7cca8c67f71254006d9714868ce266b3fa6821339ce727fc1`
(`ledger/buildlogs/20260822T074354-1172651.log`). Independent canonical replay is green
(`ledger/buildlogs/20260822T074437-1173264.log`).

The real Release `blender_browser` target recompiles and links the backend successfully, then ends
at exact locked-Ninja no-work (`ledger/buildlogs/20260822T074525-1174328.log` and
`ledger/buildlogs/20260822T075052-1179911.log`). The resulting JS, Wasm, and data SHA-256 values
are `83c0a22a5cc071c8349055af3f87a2eab937c74536c807bf6f102097d15606f4`,
`c47ffced6a427733a2dfff6da4e32ead6b4f60c420400dfc89a38ab221786258`, and
`09e58a25849eb6290a181141f5f83f928f469fe1e4d9fbdba23210bcada5a351`.
Exact REUSE 6.2.0 is green for 2,052/2,052 files
(`ledger/buildlogs/20260822T075556-1183980.log`).

Required M3 remains honestly red for the absent fresh strict candidate at
`2026-08-22T07:53:55Z`. The full regression at `2026-08-22T07:54:03Z`/`07:54:04Z` leaves every
milestone red: M0 is 3/6 because the current checkout lacks its native Blender oracle and
`oiiotool`; M1-M3 lack the fresh strict candidate; and M4-M8 retain their existing browser-pixel,
deferred-product, render-run, staged-files, and technical-release boundaries. No harness result is
promoted by this device-free task.

## Boundary

The contract creates no WebGPU instance, adapter, device, texture, sampled image, pixel, browser
receipt, or milestone result. A live swizzled sample remains owned by `M3-LINUX-REPLAY` and requires
the s7 hardware adapter; ornith-lab still exposes only llvmpipe.
