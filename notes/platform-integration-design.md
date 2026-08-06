<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# Platform integration design — account model library, "Open with", auto-save (driver, 2026-08-07)

Sketch for the (proprietary, platform-side) layer around the port. Records the
integration surface so platform work can start independently of the milestone track.

## The load-bearing fact: Blender IS the SSOT

The `.blend` file + DNA serialization is the canonical model state, with decades of
versioning discipline (we verified `blo_do_versions` 2.30→4.2 corpus parity at M1).
The platform never re-models Blender state — it stores, lists, and moves `.blend`
bytes, and drives Blender through its own APIs.

## Integration points (ALL platform-side; ZERO new upstream patches)

1. **Storage seam = OPFS (M7's project store).** Local persistence is OPFS
   (measured 0.5–1 GB/s, persistence proven). Account sync = platform JS mirroring
   OPFS dirs ↔ account storage. Blender's own autosave timers write `.blend` into
   the OPFS user dir — the platform watches + uploads. Recent files: Blender's own
   recent-files list lives in the OPFS config dir; mirror or supersede platform-side.
2. **"Open with" = a URL.** The app is a URL; deep-link `?open=<model-id>`: shell
   fetches bytes → writes to OPFS/WasmFS → invokes the open operator. Round-trips
   through the same seam.
3. **Scripting superpower:** `bpy` is fully embedded — the platform can drive
   imports/exports (glTF for the game engine — launch-tier addon; OBJ/USD at M7),
   thumbnails, and scene queries via injected Python. Anything Blender can do,
   the platform layer can script.
4. **Isolation pattern (licensing-clean + architecturally clean):** the Blender app
   page is its own GPL-complete artifact; the platform SPA talks to it at arm's
   length (URL params, postMessage, storage) — platform code stays separate.
   Do NOT link platform JS into the app page's module graph.

## Cautions

- **Trademark (D-7):** the button is "Open in <OurName>" with descriptive
  "powered by Blender" text — the mark never leads the feature name.
- **GPL boundary:** anything compiled/linked into the app artifact is GPL; keep
  platform logic on its side of the postMessage boundary.
- **Portability verdict from the record:** upstream is remarkably portable —
  ~50 small patches over 3.8M LOC (mostly build glue + the new backend), Cycles
  compiled with zero source changes, numpy with zero patches. The patch surface
  stays minimal because the extension seams (GHOST, GPUBackend, creator args,
  Python) are real seams upstream maintains.
