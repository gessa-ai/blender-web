<!--
SPDX-FileCopyrightText: 2026 blender-web contributors
SPDX-License-Identifier: CC0-1.0
-->

# M2.6.pre — tier-(b) suite selection + native oracle baselines

Prep for the **tier-(b) gate** (GOAL.md:16): Blender's stock `--background
--factory-startup` Python operator/bpy-API suites must run on the wasm build and
match the native oracle. This note is the ORACLE half: the runnable-NOW subset,
its baselines, the LFS-blocked list, and the scope-check design for the driver to
install into `harness/` later (I do NOT touch `harness/`).

Status: **oracle baselines GREEN**. Two waves: (1) 43 zero-data candidates; (2) after the
driver-approved LFS pulls (CHEAP 38.4 MB / 89 files + the imbuf_io 19 MB follow-on, both
executed — see §4), 38 more candidates, **all 38 oracle-green**. **CORE gate = 75 suites**
(939 unittest cases + 15 exit-code suites). Only 1 suite is design-excluded (`bundled_modules`)
+ 5 held wasm-AMBER. **WASM HALF FIRED** (§6): with `import bpy` green on the wasm build, the
75-suite CORE ran on `blender.js`. After the OIIO-ustring/tEXt fix (f7ec391) + the bhead
ADR-004 landing: **55/75 pass on exit code (55/61 = 90.2% after excluding 14 config-AMBER /
ADR-004-deferred); only 6 genuine open — 3 essentials asset-storage (in-flight) + 3 float-ULP
(deferral)**. See §6 for the running scoreboard.

## 1. Registration mechanism (cited)

- **Invocation profile** — `upstream/tests/CMakeLists.txt:56` (`TEST_BLENDER_EXE_PARAMS`)
  + `:69` (`_NO_THUMB`). Every `add_blender_test` runs:
  ```
  <blender> --background --console-crash-handler --factory-startup --debug-memory \
    --debug-exit-on-error --python-exit-code 1 \
    --python-expr "import bpy;bpy.context.preferences.filepaths.file_preview_type='NONE'" \
    --python <script> [-- <args>]
  ```
  `oracle/bpy.sh` already prepends `-b --factory-startup`; `sandbox/tierb-prep/run_suite.sh`
  appends the rest verbatim → an exact `add_blender_test` reproduction.
- **Registration fns** — `upstream/tests/python/CMakeLists.txt`: `add_blender_test` (:49,
  background, THE tier-b vehicle), `add_blender_test_allow_error` (:60, drops
  `--debug-exit-on-error`), `add_render_test`/`add_python_test` (:164,178, GPU render
  harness run OUTSIDE blender — tier-c, excluded), `add_system_python_test` (:190),
  `add_blender_test_ui` (:138, headed GUI via `tests/utils/blender_headless.py`, tier-c).
- **Key gate** — `TEST_SRC_DIR_EXISTS` = `IS_DIRECTORY tests/files/render`
  (`CMakeLists.txt:17`). In OUR checkout `tests/files/render` EXISTS as a directory of
  Git-LFS **pointer stubs**, so the gate reads TRUE at configure but the `.blend`/asset
  inputs are 130-byte stubs → **configure-enabled ≠ runtime-runnable**. Runnability is
  therefore decided by the SCRIPT's actual runtime inputs, not the CMake gate.

## 2. Inventory + classification

`add_blender_test` registration STATEMENTS: **125** (124 active, 1 `if(FALSE)`-disabled).
- **42 unconditional**, **65 `TEST_SRC_DIR_EXISTS`-gated**, **17 other-`WITH_*`-gated**, **1 disabled**.
- Two macro-expanders inflate the concrete count: `blendfile_versioning` `foreach 0..127`
  → **128** tests; `geo_node_test`/`geo_node_sim_test` `file(GLOB)` over
  `modeling/geometry_nodes/**` → N (0 without data).

Asset classification of the whole `tests/files` tree: **6299 Git-LFS pointer stubs,
0.76 GB real content undownloaded** (`git lfs ls-files -s -I tests/files`). Every stub is
130 bytes `version https://git-lfs.github.com/spec/v1 …`. So EVERY suite whose script opens
an external `.blend`/asset is **blocked-on-LFS** right now.

Per-script runtime-input verdict (grep evidence): **NO** = pure python / procedural data /
factory-startup only; **SELF** = writes its own temp `.blend` then reloads (no external
asset); **YES** = opens an external `.blend`/asset or takes a required `--testdir` pointing
at real data. The runnable-NOW subset = {NO, SELF} scripts that also avoid network, GPU, and
the desktop third-party bundle.

### (c) GPU/UI-excluded (tier-c, not tier-b)
All `add_render_test`/`add_python_test` render suites (cycles/eevee/workbench/overlay/
storm/compositor-GPU/sequencer-render/sculpt-render/svg/screenshot), all `add_blender_test_ui`
GUI suites, and `script_pyapi_gpu_{opengl,metal,vulkan}` (need a live GPU backend). Excluded
by definition.

## 3. Runnable-NOW subset (oracle baselines GREEN)

Scripts + args in `sandbox/tierb-prep/suites.tsv`; normalized outputs in
`sandbox/tierb-prep/baseline-<name>.txt`; verdicts in `results.tsv`; reproduce with
`sandbox/tierb-prep/run_all.sh` (79 active rows, total per-suite wall ~112s / ~2m wall-clock).
`count` = unittest cases; `exit` = custom suites gated on exit-code only.

The table below is WAVE 1 (43 zero-data candidates). WAVE 2 (§5) adds 35 more CORE suites
unlocked by the CHEAP LFS pull. The `run_suite.sh` manifest grew a 4th `mode` column
(`normal` | `allow_error` | `blend`) to cover allow_error tests and the positional-`.blend` /
`--python-text` invocation shapes; wave-1 rows are unchanged (mode defaults `normal`, same
byte-identical invocation → same baselines).

### CORE gate (38 suites — pure bpy-API/data, wasm-plausible, deterministic)

| suite (ctest name) | script | count | wall |
|---|---|---|---|
| script_pyapi_bpy_app | bl_pyapi_bpy_app.py | 1 | 2.0s |
| script_pyapi_bpy_app_tempdir | bl_pyapi_bpy_app_tempdir.py | 5 | 2.2s |
| script_pyapi_bpy_path | bl_pyapi_bpy_path.py | 1 | 2.0s |
| script_pyapi_bpy_utils_units | bl_pyapi_bpy_utils_units.py | 2 | 2.0s |
| script_pyapi_mathutils | bl_pyapi_mathutils.py | **180** | 2.1s |
| script_pyapi_bpy_driver_secure_eval | bl_pyapi_bpy_driver_secure_eval.py | 14 | 1.9s |
| script_pyapi_idprop | bl_pyapi_idprop.py | 39 | 2.1s |
| script_pyapi_idprop_datablock | bl_pyapi_idprop_datablock.py | exit | 3.2s |
| script_pyapi_prop | bl_pyapi_prop.py | 35 | 1.8s |
| script_pyapi_prop_array | bl_pyapi_prop_array.py | 42 | 1.9s |
| script_pyapi_text | bl_pyapi_text.py | 5 | 1.5s |
| script_pyapi_bmesh | bl_pyapi_bmesh.py | 12 | 1.9s |
| script_pyapi_grease_pencil | bl_pyapi_grease_pencil.py | 26 | 1.5s |
| script_pyapi_annotations | bl_pyapi_annotations.py | 15 | 1.2s |
| id_management | bl_id_management.py | 8 | 4.8s |
| bl_rna_paths | bl_rna_paths.py | 2 | 2.1s |
| bl_rna_accessors | bl_rna_accessors.py | 1 | 2.2s |
| imbuf_py_api | bl_imbuf_py_api.py | 80 | 2.3s |
| operator_function_py_api | bl_operator_function_py_api.py | 33 | 1.9s |
| operator_wrap_py_api | bl_operator_wrap_py_api.py | 48 | 1.9s |
| blendfile_io | bl_blendfile_io.py `--output-dir` | exit | 2.1s |
| global_undo | bl_global_undo.py `--src-test-dir --output-dir` | exit | 2.1s |
| geometry_attributes | bl_geometry_attributes.py | 16 | 2.3s |
| mesh_join | mesh_join.py | 10 | 2.0s |
| object_edit | object_edit.py | 1 | 2.6s |
| object_api | bl_object.py | 1 | 1.7s |
| node_tools | bl_node_tool.py | 4 | 1.4s |
| compositing_node_group | compositing_node_group.py | 1 | 0.9s |
| sequencer_strip_naming | sequencer_strip_naming.py | 6 | 0.9s |
| bl_brush | sculpt_paint/brush_asset_test.py | 4 | 1.3s |
| bl_voxel_remesh | sculpt_paint/voxel_remesh_test.py | 2 | 2.1s |
| bl_sculpt_brush_curve_presets | sculpt_paint/brush_strength_curves_test.py `--testdir` | 9 | 2.9s |
| bl_animation_bake | bl_animation_bake.py | 5 | 1.6s |
| bl_animation_rename | bl_animation_rename.py | 4 | 1.5s |
| bl_animation_nla_strip | bl_animation_nla_strip.py | 7 (1 xfail) | 2.0s |
| bl_animation_pose_slide | bl_animation_pose_slide.py | 11 | 1.4s |
| script_load_keymap | bl_keymap_completeness.py | exit | 1.4s |
| script_validate_keymap | bl_keymap_validate.py `--relaxed` | exit | 10.8s |

Wave-1 core totals: **~595 unittest cases across 33 counted suites + 5 exit-code suites** (the
CORE grand total after wave 2 is **939 unittest cases + 15 exit-code suites** across 75 suites).
Wall-time long poles: `script_validate_keymap` 10.8s, `id_management` 4.8s; everything else
≤3.2s. `global_undo`/`bl_sculpt_brush_curve_presets` accept a `--testdir/--src-test-dir` arg
but do NOT read its content at runtime (verified: pass against the stub tree, exit 0) — the
path only needs to exist.

Notes on procedural-vs-required-arg: `bl_sculpt_brush_curve_presets`, `bl_animation_*` bake/
rename/nla/pose_slide build their own data (`primitive_*_add`, `armature.new`) — no external
`.blend`. `blendfile_io`/`global_undo`/`idprop_datablock` are SELF (write temp `.blend` to the
output dir, reload, assert). `bl_brush` loads only the **bundled** essentials brush asset that
ships in `release/datafiles` (present in `BLENDER_SYSTEM_DATAFILES`), not `tests/files`.

### AMBER (oracle-GREEN but wasm-CONDITIONAL — hold out of the first gate)

| suite | oracle | wasm blocker |
|---|---|---|
| script_pyapi_doc_gen | PASS (40.97s) | pure, but **41s** — cost-prohibitive per iteration; RNA-doc completeness, low tier-b value. Optional. |
| script_load_addons | PASS | enables ALL bundled add-ons; many `import numpy` → **numpy disabled on wasm** (m2-python-boot.md: `WITH_PYTHON_INSTALL_NUMPY OFF`). Will partial-fail until numpy is harvested. |
| script_load_modules | PASS | same numpy-class import surface across `scripts/modules`. |
| script_disk_file_hash_service_test | PASS (12) | uses `_bpy_internal.disk_file_hash_service.backend_sqlite` → **sqlite3**, which m2-python-boot.md disabled (`py_cv_module__sqlite3=n/a`). Blocked until sqlite3 re-enabled. |

### EXCLUDED — not applicable to the web build (parity-theater if gated)

| suite | reason |
|---|---|
| script_bundled_modules | Asserts presence of the FULL desktop third-party bundle it imports (`numpy, requests, zstandard, sqlite3, bz2, cython, certifi, urllib3, cattrs, fastjsonschema, docutils, _blake2, pxr/USD, MaterialX, OpenImageIO, PyOpenColorIO, openvdb, oslquery`). The web build ships a reduced set BY DESIGN (GOAL "trimmed payload"; m2-python-boot.md disables most). Passes natively, guaranteed-fail on wasm — meaningless as a parity gate. |
| script_http_downloader | network egress; non-deterministic and against sandbox posture. |
| script_pyapi_blf_{buffer,vfont} | "unconditional" in CMake but `blf.load(tests/files/blenfont/…otf)` + reference renders → **blocked-on-LFS** (see below), not pure. |

## 4. Blocked-on-LFS quantification + the CHEAP pull (EXECUTED)

Background suites are blocked purely because their `.blend`/asset inputs are LFS stubs. Sizes
computed from the pointers' `size` fields:

| bucket | size | files | unlocks |
|---|---|---|---|
| **FULL** `--include=tests/files` | **0.76 GB** | 6299 | everything below (disk floor 8 GiB — trivially fits) |
| **tier-b-relevant** subset | **302.4 MB** | 1565 | all background operator/data suites |
| ↳ of which `modeling/geometry_nodes` | 173.2 MB | 411 | `geo_node_test` GLOB (~24 categories → many concrete tests) + `geo_node_sim_test` |
| **CHEAP tier-b** (excl. modeling/seq/io) | **38.4 MB** | 89 | ~35–40 suites: all `bl_animation_*` (animation/, drivers/fcurves/shapekey/keyframing/motion_path/action/armature/pose_assets/rigging_symmetrize/vertex_group_painting), all `bl_node_*` inference/interface/compat/copy/link_drag (node_group/), sculpt/paint (sculpting/ + mesh_paint/: mask/face_set/multires/mesh_filter/automask/voxel_remesh_compare + 4 paint-brush suites), physics cloth/softbody/dynamic_paint/particle×2/deform_modifiers (physics/), `bl_constraints` (constraints/), `blendfile_liblink`/`relationships`/`library_overrides` (libraries_and_linking/), `mesh_validate` (invalid_blendfiles/ + sculpting/), `object_modifier_array` (modifier_stack/) |
| **NON-tier-b** (render/ffmpeg/BGE/tracking/GPU/usd/alembic/imbuf/…) | 447.0 MB | 4734 | tier-c or excluded deps — never needed for tier-b |

**CHEAP pull — DONE (driver-approved).** Executed:
```
git -C upstream lfs pull --include="tests/files/{animation,node_group,sculpting,mesh_paint,\
  physics,constraints,libraries_and_linking,invalid_blendfiles,modifier_stack}/**"
```
Post-pull VERIFY (all held): `git -C upstream status --porcelain` line count **29 → 29**
(LFS smudge did NOT dirty status), HEAD still `fbe6228777e7`, spot-checks real content
(`constraints.blend` 933 KB `BLENDER` magic; `cloth_test.blend`/`nodegroup36.blend` Zstd `.blend`).
17.9 s, disk floor untouched (74 GiB free). It roughly DOUBLED the CORE suite count (38 → **73**).

**imbuf_io follow-on — DONE (driver-approved).** `git -C upstream lfs pull
--include="tests/files/imbuf_io/**"` (19 MB). Verify held: porcelain **29 → 29**, HEAD
`fbe6228777e7`, the referenced image is now real (`imbuf_io/reference/jpeg-rgb-90__from__rgba08.jpg`
5165 B, `ffd8ff` JPEG magic). This unlocked `blendfile_liblink` + `blendfile_relationships`
(§5 — both now green, 0 image errors / 0 aborts) → they join CORE.

Remaining for later (driver decision): the 173 MB `modeling/geometry_nodes` GLOB + the 128-test
`blendfile_versioning` corpus (needs the whole-tree root incl. render/) follow once
geometry-nodes / versioning parity is in scope. The 447 MB non-tier-b bucket
(render/ffmpeg/BGE/GPU) should never be pulled for this gate.

## 5. WAVE 2 — CORE additions unlocked by the CHEAP pull

38 candidates baselined; after the imbuf_io follow-on pull **all 38 are oracle-green**. Of these,
1 is wasm-AMBER (`physics_ocean`) → **37 join CORE** (CORE 38 → **75**). All background-capable,
no GPU render. Full per-suite rows in `results.tsv`; args + mode in `suites.tsv`.

| group (data subdir) | suites | cases |
|---|---|---|
| animation (`animation/`) | armature 6, drivers 17, shapekey 4, fcurves 17, action 32, keyframing 27, motion_path 4, pose_assets 3, rigging_symmetrize 8, vertex_group_painting 2 | 10 suites / 120 |
| geo-node groups (`node_group/`) | structure_type_inference 11, socket_usage_inference 1, group_compat 6, group_interface 25, copy_operators 5, link_drag 4 | 6 / 52 |
| sculpt/paint (`sculpting/`,`mesh_paint/`) | mask 8, face_set 3, multires 5, mesh_filter 12, automasking 2, sculpt_brushes 65 (skip 7), vertex_paint 8, weight_paint 4, texture_paint 1 (skip 1), voxel_remesh_compare (exit) | 10 / 108 |
| physics (`physics/`, positional `.blend`) | cloth, softbody, dynamic_paint, particle_system, particle_instance — all custom mesh_test (exit-code; e.g. cloth bakes ClothSimple+ClothSpring, "Mesh Comparison: Same") | 5 / exit |
| constraints (`constraints/`) | bl_constraints 14 | 1 / 14 |
| library link / override / relationships (`libraries_and_linking/` + `imbuf_io/`) | blendfile_liblink, blendfile_relationships, blendfile_library_overrides — all custom exit-code (link/append/save-reload + user-map relations) | 3 / exit |
| mesh validate (`invalid_blendfiles/`+`sculpting/`, allow_error) | mesh_validate 15 | 1 / 15 |
| modifier stack (`modifier_stack/`, `--python-text`) | object_modifier_array (gtest `[PASSED]`, exit) | 1 / exit |

Wave-2 CORE: **37 suites / 309 unittest cases + 10 exit-code suites**. Notes: `sculpt_brushes`
and `texture_paint_brushes` self-skip GPU-only brushes in `--background` (7 / 1 skips) —
deterministic, and the SAME skips will apply on wasm (no GPU backend until M3), so it is
_more_ wasm-stable, not less. `physics_*` are CPU-only sims (no GPU) — wasm-plausible.

### Wave-2 classification notes

- `blendfile_liblink` + `blendfile_relationships` initially aborted (exit 134 SIGABRT) because
  their linked `.blend` (via `--src-test-dir @SRC@/`) transitively references real images under
  `tests/files/imbuf_io/reference/` that were LFS stubs. After the **imbuf_io follow-on pull**
  (§4) both are GREEN (0 `unknown file-format`, 0 aborts; real link/save-reload + user-map
  relations execute) and are now in CORE.
- `physics_ocean` — oracle-GREEN but **wasm-AMBER**: `WITH_MOD_OCEANSIM OFF … FORCE`
  (patches/blender_web.cmake:113) means the ocean modifier does not exist on the web build, so
  it cannot pass on wasm. Green on the native oracle only; held out of the CORE gate.

## 6. WASM GATE RESULTS — the 75-suite CORE diff-run (the actual tier-(b) fire)

Ran all 75 CORE suites on the **wasm build** (`build-wasm/bin/blender.js` under emsdk node
22.16.0, `BLENDER_SYSTEM_RESOURCES/PYTHON/DATAFILES` per notes/m2-python-boot.md; the
NODEFS.fstat `--pre-js` shim is linked into the binary). Runner `run_core_wasm.sh` →
`results-wasm.tsv`; per-suite normalized wasm output `wasm-<name>.txt`. Total wall **144 s
(~2.4 min)**, slowest `bl_node_link_drag` 17.5 s.

**PRIMARY gate (exit code): 52 / 75 GREEN.** The 23 failures are the tier-(b) SIGNAL — real
wasm-vs-native differences, characterized precisely below (first divergence cited). They fall
into 7 buckets; **12 are config-AMBER** (the web build cannot pass them by construction — same
class as `physics_ocean`), leaving **63 as the honest CORE bar: 52 green + 11 genuine
divergences (82.5%)**.

### Config-AMBER (12) — cannot pass on the current web build by construction; reclassify, don't count red
- **numpy not bundled (8)** — the suite's own `import numpy` fails (`WITH_PYTHON_INSTALL_NUMPY OFF`,
  m2-python-boot.md). Not a Blender divergence; passes the moment numpy is harvested. Suites:
  `script_pyapi_prop_array`, `bl_sculpt_brush_curve_presets`, `bl_sculpt_mask`,
  `bl_sculpt_face_set`, `bl_sculpt_mesh_filter`, `bl_sculpt_automasking`,
  `bl_vertex_paint_brushes`, `bl_weight_paint_brushes`. (Joins the existing numpy-AMBER set.)
- **feature compiled OFF (4)** — forced OFF per GOAL: `bl_voxel_remesh` + `bl_voxel_remesh_compare`
  (OpenVDB OFF → "Voxel remesher failed to create mesh"), `bl_multires` (OpenSubdiv OFF →
  Multires "Disabled, built without OpenSubdiv" then `multiresModifier_subdivide_to_level`
  **crashes** — a skip-not-crash robustness bug worth filing), `bl_node_link_drag` (Cycles OFF →
  `enum "CYCLES" not found in ('BLENDER_EEVEE','BLENDER_WORKBENCH')`).

### Genuine wasm divergences (11) — the valuable tier-(b) findings (file as M2-followup / M3)
- **Float precision (3)** — cross-platform numeric (Blender vectors are float32; wasm `acosf`/libm
  rounds differently): `script_pyapi_mathutils` `test_orthogonal` `bl_pyapi_mathutils.py:666`
  `1.570796251296997 != 1.5707963267948966` (Δ 7.5e-08, `assertAlmostEqual` places=7);
  `script_pyapi_bmesh` (failures=2: `651.346363723278 != 651.346448` Δ 8.4e-05, + one
  set-membership diff); `bl_constraints` (Object-Solver constraint matrix
  `0.20000046 != 0.19999939` Δ 1.07e-06 at [1][3]). Likely need a relaxed wasm tolerance or a
  libm review — a genuine parity datum.
- **libpng tEXt "invalid keyword" on PNG write (3)** — the wasm libpng/OIIO write path rejects a
  tEXt metadata keyword → `PNG write error: tEXt: invalid keyword` → suite fails/crashes. One
  bug fixes all three: `imbuf_py_api`, `script_pyapi_idprop_datablock`, `blendfile_relationships`.
- **`.blend` readfile corruption on wasm32 (1)** — `bl_node_structure_type_inference`:
  `Blendfile corruption: Invalid, or multiple bhead with same old address value (0xefec4e70)` →
  `Aborted()`. Same 64→32 pointer/DNA family as the master_collection fix (patch 0014), resurfacing
  on real node-group `.blend`s. **Highest-value bug** — likely mis-reads other files silently too.
- **essentials-asset (3)** — `object_edit` (`test_auto_smooth_detection`), `bl_brush` (4 errors),
  `bl_sculpt_brushes`. TWO layers, investigated in §6a: (a) **PAYLOAD — FIXED**: the error was
  `No asset found at path ""` (empty) because `essentials_directory_path()` =
  `BKE_appdir_folder_id(BLENDER_SYSTEM_DATAFILES,"assets")` (essentials_library.cc:121) and the
  source `release/datafiles` ships NO `assets/` (the real essentials `.blend`s live LFS-stub'd
  at `upstream/assets/`). (b) **GENUINE DIVERGENCE — remains**: after the payload fix the path
  resolves and the `.blend` reads fine (64 brushes via `libraries.load`), yet
  `brush.asset_activate(ESSENTIALS)` still returns "No asset found" — `asset::list::
  storage_fetch_blocking(all_library_reference)` (brush_asset_ops.cc:65) does not populate the
  asset list on wasm even in blocking `G.background` mode. A wasm asset-system / threaded
  library-scan divergence, not payload.
- **node-socket type undefined (1)** — `bl_node_copy_operators` `test_ungroup`
  (`test_ungroup_proxy_nodes`), `bl_node_copy_operators.py:426`
  `assertEqual(test_socket.bl_idname, …)` → `'NodeSocketUndefined' != 'NodeSocketFloat'` (×4).
  **NOT a network socket** (it is a Blender node-tree socket `bl_idname`) and **NOT the bhead
  readfile bug** (0 corruption lines in its log): a genuine node-system divergence — a
  node/socket type resolves to `Undefined` after the node-group *ungroup* operator on wasm.

### 6a. Follow-on triage — essentials-asset + node-socket (driver-assigned)

Took the two non-big-fix divergences to root cause + right-layer disposition.

**essentials-asset → PAYLOAD FIX LANDED (+ deeper divergence pinned).** Mechanism cited above.
Fix implemented at the payload layer: `git -C upstream lfs pull --include="assets/**"` (11.3 MB /
150 files, LFS; the essentials `.blend`s were stubs) + `run_suite_wasm.sh` now composes a
datafiles dir (`_datafiles_wasm/` = `release/datafiles` symlinks + `assets/ → upstream/assets`)
so `<DATAFILES>/assets` matches a real install. Evidence it worked: the `asset_activate` error
moved from `path ""` to the full resolved path, and the essentials `.blend` loads 64 brushes via
`libraries.load`. **This is the correct payload packaging** — the shipping wasm build must place
`assets/` in its datafiles payload (porcelain stayed patch-series-only after the pull: 30 → 30,
HEAD `fbe6228777e7`).

**Deeper root-cause of the residual divergence (driver follow-on).** Traced
`storage_fetch_blocking` → `AssetList::ensure_blocking` → `filelist_readjob_blocking_run`
(filelist_readjob.cc:265) → `filelist_readjob_start_ex(…, force_blocking_read=true)` which runs
the read **single-threaded inline** (filelist_readjob.cc:227-235, `filelist_readjob_startjob` +
`endjob` directly). The read is `filelist_readjob_recursive_dir_add_items` →
`filelist_readjob_list_lib` = `BLO_blendhandle_from_file` + `BLO_blendhandle_get_datablock_info`
(filelist_readjob_common.cc:576/598). The "No asset found" is raised at asset_menu_utils.cc:128
*after* `list::is_loaded` is TRUE — the list loaded but nothing matched the weak-reference.

**GROUND-TRUTH ISOLATION (decisive):** ran `brush_asset_test.py` on the NATIVE oracle pointed at
the SAME composed `_datafiles_wasm` (`BLENDER_SYSTEM_DATAFILES=…/_datafiles_wasm`) → **PASS (OK,
exit 0)**. Same data, same paths, same test → passes native, fails wasm. So the divergence is the
**wasm runtime**, not payload/data/path. Systematically EXCLUDED:
- payload/path — native+composed passes; `system_resource('DATAFILES')` + `os.listdir` + `os.stat`
  all correct on wasm;
- asset indexer — `preferences.experimental.use_asset_indexing=False` does not fix it;
- job/threading — the blocking path is single-threaded inline (no WM_jobs / worker);
- readfile/bhead family — `--debug` run emits **0** read/`bhead`/corruption errors during the scan
  (so NOT the same bug as node_structure_type_inference), and a direct `libraries.load(
  assets_only=True)` returns 64 brushes fine.

**STOP — with evidence (architectural, not payload).** The scan runs clean yet the ESSENTIALS/All
asset list ends up without the requested asset on wasm, isolated to the C++
`filelist_readjob_list_lib` / `BLO_blendhandle_get_datablock_info` asset-listing path. Localizing
empty-list vs weak-ref-identifier-mismatch requires C-level instrumentation + a wasm rebuild
(beyond boot-recipe probing) — a source/rebuild task for the python-wasm lane, NOT fixable at the
payload/invocation layer. Payload half is fixed and shipping-relevant; the residual is one named,
well-bounded wasm asset-listing divergence.

**node-socket → HYPOTHESIS CORRECTED, kept as genuine divergence.** The driver's steer
(network-socket / stdlib syscall → possible config-AMBER) does **not** hold: the honesty
discipline requires a cited mechanism, and the mechanism (`bl_node_copy_operators.py:426`
comparing a node-tree socket `bl_idname`; 0 bhead lines) shows it is a Blender node-system issue,
not a JS/network gap. It is therefore NOT reclassified as by-design — it stays a genuine divergence
needing a node-registration/ungroup root-cause (separate follow-up; not payload-fixable).

Net: neither collapses to "closed", but essentials is narrowed from *missing data + unknown* to
*payload-fixed + one named asset-system code path*, and the node-socket premise is corrected. The
honest m2b divergence set is now **5 classes**: bhead readfile (big fix, other lane), libpng tEXt
(big fix, other lane), float-ULP (deferral), asset-list-storage (essentials, payload dep landed),
node-ungroup socket-undefined — plus the 12 config-AMBER.

### Secondary normalized-diff — NON-authoritative (as designed)
All 75 show `DIFF` in `results-wasm.tsv` col 5, INCLUDING the 52 green. Cause: under threaded
wasm stdio the guardedalloc banner + stderr **interleave in a different order** than native
(the H-4/H-5 "stdout capture UNRELIABLE" problem), plus wasm emits extra addon-register
warnings and omits the build-hash banner. This is fundamentally non-normalizable, which is
exactly why the gate is **exit-code-primary**. `wasm-denoise.pl` + `wasm-normalize.sed` strip the
CLASSIFIED benign startup noise (OIIO `physical_memory` assert; ~28 hashlib
backend-missing tracebacks; `_multiprocessing`-missing addon tracebacks) so the diff is at
least readable, but col-5 `DIFF` is informational only — never a pass/fail authority.

### Verdict (initial run)
The gate FIRES correctly: `import bpy` + the pure-bpy-API/data suite runs on wasm and **52/75
match native on exit code**; after honest config-AMBER reclassification the bar was **52/63
(82.5%)** with **11 precisely-characterized genuine divergences**. The two actionable wasm bugs
flagged as fix-next were the `.blend` bhead-collision and the libpng tEXt write bug.

### 6b. Running scoreboard (updated as fixes land)

| event | PASS/75 | honest bar (excl. deferred) | genuine open |
|---|---|---|---|
| initial wasm fire | 52 | 52/63 (82.5%) | 11 |
| **after tEXt/OIIO-ustring fix (f7ec391) + bhead ADR-004** | **55** | **55/61 (90.2%)** | **6** |
| **M2 boundary: numpy 0033 + object_edit harness fix (this round)** | **65** | **64/64 must-pass (100%)** | **0** |

**M2-boundary integration (numpy 0033 + object_edit harness fix).** Ran the full 75 CORE
on the relinked numpy binary (`blender.wasm` 102 -> 109 MB). **65/75 PASS, ZERO
regressions** (join of committed vs new verdicts: 10 FAIL->PASS flips, 0 PASS->FAIL). The
10 flips: the 8 numpy-pending sculpt/paint suites + `object_edit` (harness datafiles-path
fix) + `bl_brush` (0031, first captured green here). The 10 remaining FAIL are ALL
deferred / config-AMBER, none genuine:
- **float32-ULP (3, deferred `float32-ulp-mathutils`)** — `script_pyapi_mathutils`,
  `script_pyapi_bmesh`, `bl_constraints`.
- **ADR-004 wasm32 (1, deferred `wasm32-64bit-blend-collision`)** —
  `bl_node_structure_type_inference`.
- **feature compiled OFF (6, deferred)** — `bl_voxel_remesh` + `bl_voxel_remesh_compare`
  (`feature-off-openvdb`), `bl_multires` (`feature-off-opensubdiv`), `bl_node_link_drag`
  (`feature-off-cycles-engine`), `imbuf_py_api` (`feature-off-avif`), and **`bl_sculpt_brushes`**
  — reclassified from PENDING_ESSENTIALS to **`feature-off-opensubdiv`** (multires_reshape
  subdiv==null abort with OpenSubdiv OFF; 642efff), per the driver's "stays feature-off-AMBER,
  do NOT count against" call.

`bl_node_copy_operators` (sanctioned FLAKY `node-ungroup-socket-flake`) PASSED — consistent.
Corpus 9/9 byte-exact + startup determinism PASS on the relinked binary (no readfile regression).

**numpy verdicts (honest).** The **8 in-CORE numpy-pending suites** (`script_pyapi_prop_array`,
`bl_sculpt_brush_curve_presets`, `bl_sculpt_mask`, `bl_sculpt_face_set`, `bl_sculpt_mesh_filter`,
`bl_sculpt_automasking`, `bl_vertex_paint_brushes`, `bl_weight_paint_brushes`) are **all GREEN** —
these are exactly what `NUMPY_HARVESTED=1` promotes. The **2 AMBER numpy suites**
(`script_load_addons`, `script_load_modules`, NOT in the 75 CORE) are **NOT numpy-promotable**:
numpy now imports fine, but they hit **additional** blockers — `ModuleNotFoundError: No module
named '_ctypes'` (libffi/_ctypes absent from the wasm CPython harvest, same
`optional-python-modules` family as sqlite3/hashlib) plus a `bl_pkg` extensions `register()`
error (`already registered as a subclass 'EXTENSIONS_OT_repo_sync'`). They stay AMBER, re-blocked
on `_ctypes` + bl_pkg, not numpy. `optional-python-modules` (ledger/deferred.json) should gain
`_ctypes` + these two suites in its impact line (driver: numpy is no longer their blocker).

**scope_m2b flag recommendations (driver to bake in):**
- `NUMPY_HARVESTED=1` — all 8 PENDING_NUMPY green.
- `ESSENTIALS_LANDED=1` — `object_edit` + `bl_brush` green. REQUIRES moving `bl_sculpt_brushes`
  OUT of `PENDING_ESSENTIALS` INTO `DEFERRED[bl_sculpt_brushes]=feature-off-opensubdiv` (id
  already exists), else `core_green` goes RED on it. Net `PENDING_ESSENTIALS="object_edit bl_brush"`.
- floor: bump `core_green`'s `-ge 54` to **`-ge 64`** (must-pass total after both flips = 64/64 green).
- `deferral_consistency` is satisfied: all 7 referenced ids exist in `ledger/deferred.json`.

The OIIO-`ustring::string()`-empty-on-wasm fix (f7ec391) flipped **3** suites green:
`script_pyapi_idprop_datablock`, `blendfile_relationships` (both libpng-tEXt PNG-write), and —
via the shared string-interning path — **`bl_node_copy_operators`** (the node-socket
`NodeSocketUndefined` divergence RESOLVED, exit 0 / 5 tests OK; the "node-socket in-flight" item
is CLOSED). `imbuf_py_api` no longer crashes — its 3 residual errors are all **AVIF** writes
(`Unable to write image file`), i.e. the AVIF codec (libaom) is absent from the wasm dep harvest
→ reclassified from the libpng bucket to **config-AMBER (feature-OFF)**. The libpng-tEXt genuine
bucket is now **0**.

Separately the **bhead** fix landed as **ADR-004**: `bl_node_structure_type_inference` no longer
`Aborted()` — it now returns a clean, graceful error ("Cannot open this 64-bit .blend on 32-bit
WebAssembly: block address … collides … known wasm32 limitation (ADR-004, wasm32-pointer-collision);
a wasm64 build reads this file correctly"). Reclassified from a crashing genuine bug to an
**ADR-004 wasm32 deferral** (wasm64 escape hatch, per GOAL "wasm32 first; wasm64 later").

**Current m2b math (55/75):** 14 deferred/config-AMBER — 8 numpy (numpy not harvested), 5
feature-OFF (OpenVDB voxel-remesh ×2, OpenSubdiv multires, Cycles node_link_drag, **AVIF**
imbuf_py_api), 1 ADR-004 (node_structure_type_inference) — plus **6 genuine open**: 3 essentials
asset-storage (`object_edit`, `bl_brush`, `bl_sculpt_brushes`, in-flight in the python-boot lane,
§6a) and 3 float-ULP (`mathutils` 7.5e-8, `bmesh` 8.4e-5, `bl_constraints` 1.07e-6, deferral). If
the ULP deltas are deferred too (sub-1e-6 CPU float, a relaxed-tolerance decision), the only
active engineering work left on the m2b gate is the **3 essentials asset-storage** suites →
55/58 (94.8%). **Recommendation: this clears the M2 tier-(b) intent** — the driver can close
M2_DEPS_PYTHON with the 14 deferred tracked to their deps/ADR and the 6 genuine routed
(essentials in-flight; ULP a tolerance call).

## §scope-draft (for the driver to install into `harness/` — I do not touch harness/)

**Scope id:** `m2b` (tier-b). Manifest = `sandbox/tierb-prep/suites.tsv` CORE rows (**75**:
wave-1 38 + wave-2 37). Harness selects CORE only — exclude the 5 AMBER
(`script_pyapi_doc_gen` slow; `script_load_addons`/`script_load_modules` need numpy;
`script_disk_file_hash_service_test` needs sqlite3; `physics_ocean` needs WITH_MOD_OCEANSIM)
and the design-excluded `script_bundled_modules`. For the `blend`/`allow_error`-mode rows the
positional `.blend` and `--python-text` come straight from `suites.tsv` — the wasm runner must
honor the `mode` column (see `run_suite.sh`).

**wasm-side invocation deltas** (vs `oracle/bpy.sh`; from notes/m2-python-boot.md "Boot
recipe"):
- Binary: `tools/emsdk/node/22.16.0_64bit/bin/node build-wasm/bin/blender.js` replaces the
  native app. Flags identical to §1's profile. `--console-crash-handler` is a likely no-op
  under node (harmless; keep for fidelity, drop if it errors). `--debug-memory` should be
  re-confirmed benign under wasm guardedalloc; if it perturbs threaded stdio, drop it (it is
  not a correctness input).
- Env (NODERAWFS makes host absolute paths resolve directly):
  `BLENDER_SYSTEM_PYTHON=lib/wasm`, `BLENDER_SYSTEM_SCRIPTS=upstream/scripts`,
  `BLENDER_SYSTEM_DATAFILES=upstream/release/datafiles`.
- Link posture: `-sPROXY_TO_PTHREAD -sMALLOC=dlmalloc -sNODERAWFS -sEXIT_RUNTIME=1`, no JSPI
  (per the M2.3 node profile).
- **Args are binary-agnostic**: because the wasm runner uses the SAME `--python <script>` and
  `--testdir/--output-dir` host paths under NODERAWFS, `suites.tsv` needs NO wasm-specific
  edits. When LFS assets land, the same manifest rows run on wasm unchanged (no
  `--test-assets-dir` remap needed — the oracle and wasm both read the host `tests/files`).
- Output dir: point `@OUT@` at a host-writable scratch (NODERAWFS) — same as oracle.

**Comparison method — NORMALIZED, exit-code-primary:**
1. **PRIMARY gate = per-suite exit code.** `--python-exit-code 1` + `--debug-exit-on-error`
   make ANY failing assertion / unittest failure / error exit **nonzero** (verified: all 75
   core suites exit 0 on the oracle; a single failing case flips exit — indeed the imbuf_io
   transitive-stub problem surfaced exactly this way, as exit 134, before the follow-on pull).
   NOTE: `allow_error`-mode suites
   (`mesh_validate`) DROP `--debug-exit-on-error`, so for them the exit code reflects the
   script's own `--python-exit-code`, not error-reporting. This SIDESTEPS the
   known wasm-stdout-drop problem (harness note H-4/H-5, progress.txt "stdout capture
   UNRELIABLE under threaded wasm stdio") — the tier-b gate must NOT depend on scraping
   `Ran N / OK` from wasm stdout. Gate GREEN iff every core suite exits 0.
2. **SECONDARY corroboration = normalized-diff** of `wasm-<suite>.txt` vs
   `baseline-<suite>.txt`, both filtered through `sandbox/tierb-prep/normalize.sed`. Use as a
   regression detector, not the pass/fail authority. For the 60 unittest suites the meaningful
   lines are `Ran N tests …` (expected N in §3/§5) + the `OK`/`FAILED (…)` verdict + any
   traceback; for the 15 exit-code suites the normalized stdout is near-empty (banner + `quit`).
   Do NOT require exact stdout equality — build hash/date, unittest timing, temp paths
   (`/var/folders` vs `/tmp`), and hex addresses differ between native-arm64 and wasm by
   construction (that is exactly what `normalize.sed` masks).

**Normalization needed (observed, encoded in `normalize.sed`):**
1. build banner date/time (hash pinned, date varies) → `Blender <VER> LTS (hash <PIN> built <DATE>)`;
2. unittest timing `Ran N tests in <T>s`; 3. hex addresses `0xADDR` (guardedalloc/repr);
4. temp dirs `/var/folders|/private/var/folders|/tmp/…` → `<TMP>`; 5. repo-absolute paths → `<REPO>`.
6. **Watch (wasm-only, expected):** mathutils/float `repr` last-ULP differences between arm64 and
   wasm. These do NOT appear as stdout noise — `bl_pyapi_mathutils` compares against hardcoded
   expected values INSIDE the test, so any float divergence surfaces as a genuine test FAILURE
   (nonzero exit). That is the correct tier-b signal, not something to normalize away.

**Expected-counts table** for the secondary check = the `count` column in §3 (mathutils 180,
imbuf_py_api 80, operator_wrap 48, …). Store as the golden alongside the baselines.

**Roll-out:** gate on the 75 CORE first (all wasm-plausible with the CURRENT reduced stdlib).
Promote AMBER suites as their deps land (numpy → load_addons/load_modules; sqlite3 →
disk_file_hash). Grow via the CHEAP 38 MB LFS pull (§4) once background-data suites are in scope.

## Reproduce

```
sandbox/tierb-prep/run_all.sh                 # 79 active rows, ~2m, writes results.tsv + baselines
sandbox/tierb-prep/run_suite.sh <ctest_name>  # one suite
```
Raw logs + generated `.blend` land in `sandbox/tierb-prep/_out/` (gitignored). upstream left
pristine (read-only; nothing written under it).

## §scope-final — paste-ready `scope_m2b` for the harness boundary install

Driver: paste the function into `harness/run.sh` beside `scope_m1`, and change the registry
line `SCOPES_REGISTERED="m0 m1"` → `SCOPES_REGISTERED="m0 m1 m2b"` (the only other edit). It
follows the house style: `record NAME 0|1 DETAIL`, exit-code-primary robust counting (the
tier-(b) analogue of `scope_m1`'s `--gtest_output=json` — wasm threaded stdout is UNRELIABLE per
H-4/H-5, so the gate reads the process **exit code**, never scraped `OK`/`Ran N` lines),
artifact-missing FAIL with the rebuild recipe in the detail, and fast-fail honesty.

**SCOPES_REGISTERED delta:** `m0 m1` → `m0 m1 m2b` (one token added).
**Expected wall time:** ~150 s (75 CORE suites × ~2 s node cold-start each; wall-clock ~2.5 min).
The run reuses `sandbox/tierb-prep/{run_core_wasm.sh,run_suite_wasm.sh,suites.tsv,normalize.sed,
wasm-denoise.pl,_datafiles_wasm}` — all committed/idempotent; raw logs land in the gitignored
`_out/`.

Green math encoded (bump in ONE place as deps land): today **54 must-pass** (deterministic
green). Flip `ESSENTIALS_LANDED=1` when the §6a asset-storage fix lands → 57; flip
`NUMPY_HARVESTED=1` when numpy is in `lib/wasm` → +8. Each flag flip moves its named group from
"allowed-fail (pending)" to "must-pass" in a single assignment.

```bash
# ---------------------------------------------------------------- scope: m2b
# Tier-(b): Blender's stock --background --factory-startup Python operator/bpy-API CORE suite
# (75 rows of sandbox/tierb-prep/suites.tsv) run on the wasm build (build-wasm/bin/blender.js
# under emsdk node) and matched to the native oracle. EXIT-CODE is the gate signal: wasm threaded
# stdout drops lines at exit (H-4/H-5), exactly like the tier-(a) gtests, so counts come from the
# process exit code (--python-exit-code 1 + --debug-exit-on-error make any failing assert nonzero),
# never from scraped stdout. Full evidence + running scoreboard: notes/m2-tierb-prep.md §6/§6b.
scope_m2b() {
  local PREP=sandbox/tierb-prep
  local NODE; NODE="$(ls -d tools/emsdk/node/*/bin/node 2>/dev/null | head -1)"

  # --- config: bump these ONE-LINE flags as pending deps land (moves a named group to must-pass)
  local ESSENTIALS_LANDED=0   # §6a asset-storage fix -> object_edit,bl_brush,bl_sculpt_brushes (+3)
  local NUMPY_HARVESTED=0     # numpy in lib/wasm    -> the 8 sculpt/paint numpy suites          (+8)

  # --- suite classification (everything NOT listed here defaults to MUST-PASS) -----------------
  # DEFERRED (deterministic): expected to FAIL on the current build; each MUST have a matching
  #   ledger/deferred.json id. A deterministic-deferred suite that PASSES => un-defer candidate
  #   (flagged, never silently green).  suite -> deferred.json id:
  local -A DEFERRED=(
    [script_pyapi_mathutils]=float32-ulp-mathutils
    [script_pyapi_bmesh]=float32-ulp-mathutils
    [bl_constraints]=float32-ulp-mathutils
    [bl_node_structure_type_inference]=wasm32-64bit-blend-collision
    # feature compiled OFF per GOAL (OpenVDB / OpenSubdiv / Cycles engine / AVIF codec):
    [bl_voxel_remesh]=feature-off-openvdb
    [bl_voxel_remesh_compare]=feature-off-openvdb
    [bl_multires]=feature-off-opensubdiv
    [bl_node_link_drag]=feature-off-cycles-engine
    [imbuf_py_api]=feature-off-avif
  )
  # FLAKY: deferred heisenbug — EITHER outcome is consistent (no un-defer flag on a pass); id req'd.
  local -A FLAKY=( [bl_node_copy_operators]=node-ungroup-socket-flake )
  # PENDING: promise-held; allowed-fail until its dep lands, then the flag above makes it must-pass.
  local PENDING_ESSENTIALS="object_edit bl_brush bl_sculpt_brushes"
  local PENDING_NUMPY="script_pyapi_prop_array bl_sculpt_brush_curve_presets bl_sculpt_mask \
bl_sculpt_face_set bl_sculpt_mesh_filter bl_sculpt_automasking bl_vertex_paint_brushes \
bl_weight_paint_brushes"

  # --- preflight artifacts (FAIL with rebuild recipe; a rebuild is a worker action, not a side effect)
  if [ -z "$NODE" ]; then
    record wasm_runtime 0 "no emsdk node under tools/emsdk/node/*/bin/node"; return
  fi
  if [ ! -f build-wasm/bin/blender.js ]; then
    record wasm_runtime 0 "build-wasm/bin/blender.js missing; rebuild: flip WITH_PYTHON ON + \
blender_web_node_binary(blender) + ninja -C build-wasm blender (see notes/m2-python-boot.md)"; return
  fi
  if [ ! -d lib/wasm/lib/python3.13 ]; then
    record wasm_runtime 0 "lib/wasm python harvest missing; rebuild: bash scripts/deps/python.sh"; return
  fi
  record wasm_runtime 1 "$NODE ($("$NODE" --version 2>/dev/null)); blender.js + lib/wasm present"

  # --- run the 75 CORE suites (EXIT-CODE per suite -> $PREP/results-wasm.tsv). ~150 s. -----------
  # run_core_wasm.sh runs exactly the CORE set (it skips the 5 AMBER + 1 design-excluded) and
  # composes the datafiles payload idempotently. If it is absent the scope cannot proceed.
  if [ ! -x "$PREP/run_core_wasm.sh" ]; then
    record m2b_manifest 0 "$PREP/run_core_wasm.sh missing (tier-b harness kit not present)"; return
  fi
  "$PREP/run_core_wasm.sh" >/dev/null 2>&1
  local RES="$PREP/results-wasm.tsv"
  local NROWS; NROWS="$(grep -cvE '^#' "$RES" 2>/dev/null || echo 0)"
  if [ "$NROWS" != 75 ]; then
    record m2b_manifest 0 "expected 75 CORE rows, got $NROWS (suites.tsv drift?) [$RES]"; return
  fi
  record m2b_manifest 1 "75 CORE rows executed [$RES]"

  # --- classify each row by EXIT CODE (col 3). verdict col 2 is advisory; exit is the gate. -----
  local mustpass_total=0 mustpass_green=0 mustfail=""     # must-pass set
  local undefer=""                                        # deterministic-deferred that PASSED
  local undoc=""                                          # deferred/flaky suite w/o deferred.json id
  local pending_ready=""                                  # a not-yet-landed PENDING suite that PASSED
  local DEF_IDS; DEF_IDS="$(python3 -c "import json;print(' '.join(e['id'] for e in json.load(open('ledger/deferred.json'))['deferred']))" 2>/dev/null)"
  in_set() { case " $2 " in *" $1 "*) return 0;; *) return 1;; esac; }

  local name exit rest
  while IFS=$'\t' read -r name _verdict exit rest; do
    case "$name" in ''|\#*) continue;; esac
    local passed=0; [ "$exit" = 0 ] && passed=1

    if [ -n "${DEFERRED[$name]:-}" ]; then
      in_set "${DEFERRED[$name]}" "$DEF_IDS" || undoc="$undoc $name(${DEFERRED[$name]})"
      [ "$passed" = 1 ] && undefer="$undefer $name(${DEFERRED[$name]})"
    elif [ -n "${FLAKY[$name]:-}" ]; then
      in_set "${FLAKY[$name]}" "$DEF_IDS" || undoc="$undoc $name(${FLAKY[$name]})"
      # either outcome consistent -> no gate effect
    elif in_set "$name" "$PENDING_ESSENTIALS"; then
      if [ "$ESSENTIALS_LANDED" = 1 ]; then
        mustpass_total=$((mustpass_total+1)); [ "$passed" = 1 ] && mustpass_green=$((mustpass_green+1)) || mustfail="$mustfail $name"
      elif [ "$passed" = 1 ]; then pending_ready="$pending_ready $name(flip ESSENTIALS_LANDED=1)"; fi
    elif in_set "$name" "$PENDING_NUMPY"; then
      if [ "$NUMPY_HARVESTED" = 1 ]; then
        mustpass_total=$((mustpass_total+1)); [ "$passed" = 1 ] && mustpass_green=$((mustpass_green+1)) || mustfail="$mustfail $name"
      elif [ "$passed" = 1 ]; then pending_ready="$pending_ready $name(flip NUMPY_HARVESTED=1)"; fi
    else
      # default: MUST-PASS (also auto-requires any new deterministic-green suite added to the manifest)
      mustpass_total=$((mustpass_total+1)); [ "$passed" = 1 ] && mustpass_green=$((mustpass_green+1)) || mustfail="$mustfail $name"
    fi
  done < <(grep -vE '^#' "$RES")

  # --- CHECK 1: core green — every must-pass suite exits 0 (fast-fail: names the reds) ----------
  if [ "$mustpass_green" = "$mustpass_total" ] && [ "$mustpass_total" -ge 54 ]; then
    record core_green 1 "$mustpass_green/$mustpass_total must-pass CORE suites exit 0 \
(ESSENTIALS_LANDED=$ESSENTIALS_LANDED NUMPY_HARVESTED=$NUMPY_HARVESTED)"
  else
    record core_green 0 "must-pass RED $mustpass_green/$mustpass_total; failing:${mustfail:- none} \
(min-expected 54; if a suite regressed, that is the gate)"
  fi

  # --- CHECK 2: deferral consistency vs ledger/deferred.json (honest, no silent green) ----------
  local dc_detail="" dc_ok=1
  [ -n "$undoc" ] && { dc_ok=0; dc_detail="$dc_detail undocumented-deferral:$undoc (add to deferred.json);"; }
  [ -n "$undefer" ] && { dc_ok=0; dc_detail="$dc_detail UN-DEFER-candidate (deterministic-deferred now PASSES):$undefer;"; }
  [ -n "$pending_ready" ] && { dc_ok=0; dc_detail="$dc_detail PENDING-now-green:$pending_ready;"; }
  if [ "$dc_ok" = 1 ]; then
    record deferral_consistency 1 "all deferred/flaky suites map to a deferred.json id and behave as classified"
  else
    record deferral_consistency 0 "${dc_detail# }"
  fi
}
```

**Why each check exists (audit trail):**
- `wasm_runtime` — node + `blender.js` + `lib/wasm` present, else FAIL with the exact rebuild
  command (mirrors `scope_m1`'s artifact-missing recipes; a rebuild is a worker action).
- `m2b_manifest` — the run produced exactly 75 CORE rows (guards silent `suites.tsv` drift).
- `core_green` — the headline: every **must-pass** suite exits 0. Parameterized — the two
  LANDED flags move `PENDING_ESSENTIALS`/`PENDING_NUMPY` into must-pass in one assignment each; a
  hard floor (`>=54`) stops an accidental empty/short run from reading green.
- `deferral_consistency` — enforces GOAL's "deferrals are honesty, silence is fraud": every
  suite the gate lets fail must carry a `ledger/deferred.json` id; a deterministic-deferred suite
  that starts PASSING is flagged as an **un-defer candidate** (not silently green); a still-flagged
  PENDING suite that goes green tells the driver to flip the one-line LANDED flag. `bl_node_copy_
  operators` is the sanctioned FLAKE (`node-ungroup-socket-flake`, ~1.4%) — either outcome is
  consistent, so it is neither must-pass nor an un-defer trigger.

**deferred.json coverage note (action before green):** the ULP (`float32-ulp-mathutils`),
ADR-004 (`wasm32-64bit-blend-collision`) and flake (`node-ungroup-socket-flake`) ids already exist.
The four **feature-off** ids referenced above (`feature-off-openvdb`, `feature-off-opensubdiv`,
`feature-off-cycles-engine`, `feature-off-avif`) — spanning **5 suites** (`bl_voxel_remesh` +
`bl_voxel_remesh_compare` share `openvdb`) — are NOT yet in `ledger/deferred.json`; until the
driver adds them, `deferral_consistency` will (correctly, honestly) record RED naming them — that
is the gate refusing to hide an undocumented deferral, not a harness bug. numpy + essentials are
tracked as pending (promise-held), not deferrals.

**Reconciliation — in-flux socket classification (driver 184035c vs registry):** the draft
classifies `bl_node_copy_operators` as the sanctioned FLAKE because the live
`ledger/deferred.json` still carries `node-ungroup-socket-flake` (status `under-investigation`)
— i.e. it honors the registry-of-record. Driver commit `184035c` ("socket-Undefined RESOLVED —
CONFIRMED-FIXED-BY-f7ec391, reclassify GREEN") signals the intent to promote it; when the
`node-ungroup-socket-flake` entry is **removed from deferred.json**, delete the one `FLAKY=(…)`
line so `bl_node_copy_operators` falls through to must-pass — green floor 54 → 55 (bump the `>=54`
in `core_green` to `>=55`). Until the registry and the reclassification agree, `deferral_
consistency` is the seam that surfaces the drift: if deferred.json drops the flake id while the
draft still lists it, the `in_set` check flags it `undocumented-deferral` — the gate refusing to
let registry and gate silently diverge. (This is the honest handling of a genuinely concurrent
cross-lane state, not a guess at which side wins.)

**Dry-run (against the committed `results-wasm.tsv`, logic-validated without a full re-run):**
`core_green` = **54/54 must-pass green**; no un-defer candidates; `deferral_consistency` = RED
naming exactly the 5 feature-off suites (`imbuf_py_api bl_voxel_remesh bl_voxel_remesh_compare
bl_multires bl_node_link_drag`) that need deferred.json entries — i.e. the gate is one honest
edit (add the 4 feature-off ids) away from GREEN on the current build, and `core_green` already
holds. `bash -n` clean; requires bash ≥ 4 (associative arrays) — the host `bash` is 5.2.

## 7. m2b divergence dive — bug1 FIXED, bug2 root-caused (2026-08-04, integration)

### BUG1 (libpng tEXt "invalid keyword") — FIXED (commit f7ec391), clears 3 suites
NOT a libpng issue. OIIO 3.1.13.1's `ustring::TableRep` pokes libc++ `std::string`'s private
`__long` fields for long strings, assuming a layout emscripten's libc++ does NOT match →
`ustring::string()` returns EMPTY for strings >= the SSO threshold ("ResolutionUnit", 14ch, is
long on wasm32) while `c_str()` is correct. OIIO's PNG writer `put_parameter` reads
`name().string()`="" → fails to skip "ResolutionUnit" → emits a tEXt with an EMPTY keyword →
libpng "tEXt: invalid keyword" → every PNG-with-metadata write aborts. Fix: exclude
`__EMSCRIPTEN__` from that libc++ branch (as OIIO already does for aarch64), falling to the safe
`str = strref` copy — `scripts/deps/openimageio.sh` sed on `ustring.cpp`. Verify: bare imbuf PNG
write → 250 B (== native); `script_pyapi_idprop_datablock` PASS, `blendfile_relationships` PASS.
`imbuf_py_api` residual 3 errors = AVIF codec not built (config-AMBER, libaom off per GOAL).
NOTE: broad win — `ustring::string()` was silently wrong for ALL long interned strings on wasm.

### BUG2 (essentials asset "No asset found") — ROOT-CAUSED, driver territory (DNA/readfile)
Full trace (all confirmed by instrumentation, since reverted):
1. Path resolution: FIXED by the runner's composed datafiles + `BLENDER_SYSTEM_RESOURCES=upstream`
   (`BLENDER_SYSTEM_SCRIPTS` is NOT read by appdir for the main scripts; `get_path_system_ex`
   honors `BLENDER_SYSTEM_RESOURCES`). Assets are REAL (not LFS stubs).
2. The essentials library IS scanned; each `.blend` opens (`BLO_blendhandle_from_file` ok) and
   `BLO_blendhandle_get_datablock_info` returns all assets (mesh_sculpt: datablock_len=64). The
   "all" filelist reaches **raw=316** entries.
3. BUT `filelist_files_ensure` → **filtered=0**. The `FLF_ASSETS_ONLY` filter
   (`filelist_filter.cc:53`) drops every entry because they have `FILE_TYPE_BLENDERLIB` but NOT
   `FILE_TYPE_ASSET` (typeflag=0x80000000).
4. `FILE_TYPE_ASSET` is set (`filelist_readjob_common.cc:423-425`) only if
   `datablock_info->asset_data != null`. It IS null.
5. **ROOT:** in `blo_read_asset_data_block` (readfile.cc), `asset_meta_data` is non-null after
   `blendhandle_load_id_data_and_validate` (the raw file-address from
   `blo_bhead_id_asset_data_address`) but `BLO_read_struct(&reader, AssetMetaData, r_asset_data)`
   (newdataadr / oldnewmap) resolves it to **NULL** — the AssetMetaData DATA-block pointer does
   not resolve when reading a 64-bit `.blend` on wasm32 via the blendhandle partial-read path.
   This is the **64→32 pointer-resolution family** (same class as the driver's patch 0014
   master_collection fix), resurfacing for AssetMetaData in the lightweight blendhandle reader.
   → **STOP (driver): DNA/readfile.** The full readfile (corpus 9/9) works; only this partial
   blendhandle asset-metadata read path mis-resolves.
6. SECONDARY poison: the asset indexer caches per-`.blend` `.index.json` in
   `~/.cache/blender/asset-library-indices/`. The FIRST failed read wrote a 13-byte EMPTY index
   (`entries:None`); every later run then loads that empty index and skips the `.blend` read
   entirely. Clearing that dir lets the read proceed (to the still-null asset_data). Any real fix
   must also invalidate/clear the poisoned indices.

### BUG3 (NodeSocketUndefined) — NOT STARTED (time spent on bug2 dive).
