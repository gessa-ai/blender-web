<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# Patch 0146 static and deferred probe plan

## Frozen static checks

1. Require the patch to name exactly one source path:
   `source/blender/draw/engines/eevee/shaders/eevee_shadow_tag_update.bsl.hh`.
2. Run a read-only forward apply-check against the live baseline without applying it.
3. In a temporary isolated tree, apply the patch, reverse it to the exact baseline hash, and apply
   it again to the exact first-applied hash.
4. Inspect the patched source and require:
   - slot 8 is declared `storage(8, read)` with a const `ShadowTileMapData` array;
   - only `tag_update_vert` and `tag_update_frag` use the local read-only table;
   - `tag_propagate` still uses generic read-write `TileMaps`;
   - the fragment `Tiles` binding and `atomicOr` remain unchanged; and
   - no binding number, resource member name, index expression, or executable statement changes.
5. Run whitespace and U+2014 checks over the patch, note, probe plan, and freeze receipt. Confirm
   the shared index is empty and the live source hash is unchanged.

## Deferred stable-tree acceptance

Do not build or run these gates until 0138, 0143-A, and 0144 are committed and independently
accepted, in that order.

1. Apply 0146 to the stable source, serialize locked native and shipping wasm builds through
   `scripts/ninja-locked.sh`, and record source and artifact hashes.
2. Compile `eevee_shadow_tag_update` and inspect the emitted shader/interface receipt. Require slot
   8 to be read-only and visible to vertex and fragment, with no vertex read-write storage error.
3. Require the previous `eevee_shadow_tag_update` browser failure family to be absent, including
   the `ProgramFromIR` vertex-stage read-write storage diagnostic and its bind-group/pipeline
   cascade. Preserve all later independent errors without reclassification.
4. Verify the fragment stage still compiles and executes `atomicOr` on the slot-9 `Tiles` storage
   buffer. Verify `tag_propagate` retains its read-write tile-map behavior.
5. Run the unchanged locked native RUN-only census and static-shader census. The accepted baseline
   must hold or improve, and any denominator change must come from already accepted dependencies,
   not from this one-file declaration repair.
6. In the shipping browser, render a shadowed EEVEE scene for at least two frames, mutate a caster
   or light between frames, and require the shadow update to follow the mutation. Capture complete
   GPU error families, sentinel/readback accounting, non-black pixels, and an unchanged-golden
   comparison when the accepted render/readback stack makes that gate available.
7. Open every captured screenshot before reporting and add a `.license` sidecar for each PNG.

Phase B1 is deliberately excluded. Do not change the `MADefault_Surface_shadow_mesh`
storage-texture atomic representation or weaken EEVEE shadow readiness in this probe sequence.
