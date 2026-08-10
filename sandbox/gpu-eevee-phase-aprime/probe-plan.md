<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# Patch 0144 stable-tree probe plan

Run only after the driver declares patches 0138 and 0143 committed and the shared source stable.
Use a driver-assigned free port and never terminate a foreign browser.

1. Record the committed source hash, patch hash, full owned path list, and final native/wasm
   artifact hashes. Verify patch reverse-apply and exact reverse/forward round trip again.
2. Serialize a locked native build through `scripts/ninja-locked.sh`. Run the unchanged M3 RUN-only
   census and require 149 PASS / 7 FAIL / 2 CRASH unless the driver has accepted a newer baseline.
   Measure the static-shader receipt; the patch adds exactly 14 registered variants, so the current
   973 denominator must become 987. Record the measured numerator and every residual failure.
3. Serialize the shipping windowed wasm build through `scripts/ninja-locked.sh`.
4. Re-run the seven fresh M6 rows that previously reported RG11B10Ufloat ReadWrite BGL rejection:
   principled thin-subsurface, transparency blended, raycast visibility, and all four shadow rows.
   Preserve complete GPU error families. Require the RG11B10Ufloat ReadWrite BGL family to be zero;
   classify later RG16Unorm or Phase B atomic failures separately.
5. Run a fresh EEVEE `camera_depth_of_field.blend` gate on the final wasm binary. Require zero
   RG11B10Ufloat storage-texture bind-group-layout errors, complete render/readback accounting,
   non-black result pixels, and a passing comparison against the existing unchanged golden.
6. Run a fresh driver-selected representative EEVEE volume-corpus scene and record its exact corpus
   path and input hash. Require zero RG11B10Ufloat storage-texture bind-group-layout errors,
   complete render/readback accounting, non-black result pixels, and a passing comparison against
   the existing unchanged golden.
7. Re-run principled default and the non-shadow representative set selected by the driver. Require
   render sentinel, exact production readback hook/capture accounting from the now-stable readback
   stack, non-black result pixels, and an honest unchanged-golden comparison.
8. Re-run principled transmission twice with the same startup blend: saved Image Editor Render
   Result and an in-memory switch of that area to View3D. The Image Editor run must have zero
   writable storage alias errors at final mip. Preserve timestamp chronology relative to the render
   sentinel and readback markers.
9. Exercise one non-layered and one layered mip chain with an even mip count, including the
   128-by-128 RGBA16Float eight-mip case. Capture the final dispatch layout or equivalent Dawn
   validation receipt proving two storage bindings for the one-output variant, while an earlier
   paired dispatch retains three. Verify final-mip pixels are written and earlier mip levels are
   unchanged in behavior.
10. Open every browser screenshot before reporting. Each committed PNG requires its own `.license`
   sidecar. Do not change the harness, oracle, golden, threshold, deferral, ledger, results,
   dashboard, series, fix plan, or decisions.
