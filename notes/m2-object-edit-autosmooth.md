<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M2b — object_edit test_auto_smooth (`len(modifiers) 4 != 1`): HARNESS path, NOT a wasm bug

Date: 2026-08-05. Owner: ABI specialist. Disposition of the last M2-gate essentials item.
**VERDICT: not a wasm runtime / DNA / readfile bug — a harness datafiles-path naming issue.
No upstream code fix (no patch 0032). One-line harness fix, verified.**

## The test
`object_edit.py::test_auto_smooth_detection` calls `bpy.ops.object.shade_auto_smooth(
use_auto_smooth=True)` 4x and asserts `len(ob.modifiers) == 1` — the operator must be
idempotent (detect the existing "Smooth by Angle" geometry-nodes modifier and not re-add).
On wasm it yielded 4 modifiers.

## Root cause (instrumented, decisive)
The idempotency dedup is `is_smooth_by_angle_modifier()` (editors/object/object_edit.cc:1617).
For the appended essentials node-group (which ends up LINKED, `lib` set, `library_weak_
reference` null), it falls to the library branch (1636-1647):
```
char auto_smooth_asset_path[FILE_MAX] = "datafiles/assets/nodes/geometry_nodes_essentials.blend";
if (!StringRef(library->filepath).endswith(auto_smooth_asset_path)) return false;
```
The m2b harness (`sandbox/tierb-prep/run_suite_wasm.sh:31`) composes its datafiles dir as
`_datafiles_wasm` (release/datafiles symlinks + `assets -> upstream/assets`). So the asset's
`library->filepath` is `.../_datafiles_wasm/assets/nodes/geometry_nodes_essentials.blend`,
which ends in `_wasm/assets/...`, NOT `datafiles/assets/...` -> `endswith` FALSE ->
detection fails -> a new modifier every call.

## Ground-truth isolation (native fails identically; wasm passes when path is right)
Probe: cube + shade_auto_smooth, inspect the node-group's `library.filepath` + the endswith.
- **Native oracle + `_datafiles_wasm`**: N_MOD=2 for 2 calls, `library.filepath` ends in
  `_datafiles_wasm/assets/...`, endswith == FALSE -> SAME failure. So it is NOT wasm-specific.
- **Wasm + a datafiles dir NAMED `datafiles`** (path ends in `datafiles/assets/...`): N_MOD=1;
  the full `object_edit.py` runs `exit 0, Ran 1 test, OK`.
(The `.001` library-name suffix is a benign duplicate-name artifact and irrelevant — the
check reads `filepath`, not name.)

## Fix (harness / packaging — NOT upstream code)
`sandbox/tierb-prep/run_suite_wasm.sh`: name the composed datafiles dir so its path ends in
`datafiles` (e.g. `DATAFILES="$HERE/datafiles"` instead of `$HERE/_datafiles_wasm`), matching
a real install (`.../<ver>/datafiles/assets/...`). Owned by the m2b/tierb lane. The SHIPPING
wasm build already must place `assets/` under a `datafiles/`-ending path (same packaging
requirement flagged for essentials in notes/m2-tierb-prep.md) — this test simply asserts it.
Verified: with that, object_edit is green on wasm.

## Why not patch the upstream endswith
`is_smooth_by_angle_modifier`'s hard-coded `datafiles/assets/...` suffix is correct upstream
behavior and works for any correctly-packaged install; the bug is the harness dir name, not
the code. Touching upstream here would be special-casing a test-harness artifact. STOP-in-code,
fix-in-harness.
