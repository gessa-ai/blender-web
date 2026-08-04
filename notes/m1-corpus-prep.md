<!--
SPDX-FileCopyrightText: 2026 blender-web contributors
SPDX-License-Identifier: GPL-2.0-or-later
-->
# M1.12 — `.blend` corpus + state-dump parity (ORACLE-SIDE half)

Oracle: Blender **5.2.0 LTS**, Python **3.13.13**, build hash **fbe6228777e7**
(matches `upstream/PIN`; same commit as the wasm build). All artifacts staged
under `sandbox/corpus-prep/` as **candidates** for the driver to install into
`tests/golden/` at the milestone boundary. Nothing here writes to `tests/`.

## 1. Corpus reality (what is actually on disk)

The upstream regression corpus is **not present** — it is un-pulled Git-LFS
pointer stubs:

| location | `.blend` count | state |
|---|---|---|
| `upstream/tests/files/**` | 1965 | **all LFS pointers** (130 B `version https://git-lfs…` stubs), 0 real |
| `upstream/release/datafiles/{preview,preview_grease_pencil}.blend` | 2 | LFS pointers |
| `upstream/assets/{brushes,nodes}/*.blend` | 12 | LFS pointers |
| `upstream/scripts/startup/bl_app_templates_system/**/startup.blend` | 8 | LFS pointers |
| `upstream/release/datafiles/startup.blend` | 1 | **real** (121 KB, zstd-compressed) |

Verified by magic-byte inspection (`BLENDER` / zstd `28 b5 2f fd` / gzip `1f 8b`
vs. LFS `version https://git-`): exactly **one** real `.blend` ships in the
checkout — `startup.blend`.

**Decision:** build the corpus from `startup.blend` **plus files authored via
the oracle itself** (`generate_corpus.py` drives bpy + `wm.save_as_mainfile`).
These are *real Blender writefile output*, read back through the *real readfile
paths* on both the native oracle and (later) the wasm build — so LOAD parity is
genuine, not synthetic-parser parity. Each file is small, deterministic, and
targets a distinct blenkernel readfile subsystem. `startup.blend` is compressed
(exercises the zstd decompression path); the generated files are saved
uncompressed (exercise the raw readfile path).

## 2. Corpus chosen (9 files)

| file | source | subsystems exercised (blenkernel readfile) | notable state |
|---|---|---|---|
| `startup.blend` | shipped (upstream) | baseline default scene; **zstd decompression**; world/compositor group; view layers | objects=3 meshes=1 materials=2 lights=1 cameras=1 images=2 worlds=1 |
| `mesh_dense.blend` | generated | **CustomData layers** across all domains (POINT/EDGE/FACE/CORNER): 2 UV maps, byte-color, custom FLOAT attr, vertex group; dense topology | 10201 v / 20200 e / 40000 loops / 10000 polys; 15 attributes; + ico (tris) |
| `modifiers.blend` | generated | **ModifierData** readfile + inter-object modifier pointers | stack: Subsurf, Mirror, Array, Bevel, Solidify, Boolean→Cutter |
| `animation.blend` | generated | **slotted Action / fcurve / keyframe** readfile + **drivers** | 2 actions (9 + 1 fcurves), scripted driver `DrivenCube.z = src*2` |
| `materials_nodes.blend` | generated | **node tree / node group / socket / link** readfile; multi-slot + per-face `material_index`; fake-user orphan | 3 materials (6-node graphs), 1 shader node group `TintGroup` |
| `curves_text.blend` | generated | **Curve** datablock (TextCurve / Bezier / NURBS) + **VFont** readfile | TextCurve body `"Blender Web 5.2"`, builtin font `<builtin>`, bevel curve, nurbs path |
| `armature.blend` | generated | **Armature / Bone** rest-pose readfile + Armature modifier + vertex groups | 3-bone chain (root→spine→head), skinned cylinder |
| `collections_instancing.blend` | generated | **Collection hierarchy** + object **instancing** (dupli) readfile | nested Root>{GroupA,GroupB}, collection-instance empty |
| `stress_mixed.blend` | generated | **multi-user ID linking** + user counts + orphan handling + mixed types | 20 objects share 1 mesh (`SharedMesh.users==20`), fake-user orphans, driver, action, empty chain |

**Subsystem coverage:** mesh CustomData, modifier stack, animation
(actions/fcurves/drivers), shader nodes + node groups, curves + fonts,
armatures + deform, collections + instancing, ID linking / user counts /
orphans, plus the compressed-file baseline. This is a graduated 9-file corpus
inside the requested 6–12 band.

**What a fuller (LFS-pulled) corpus would add** and is *not* covered here:
old-version files that exercise `blo_do_versions_*` (forward-porting from
pre-5.2 DNA — the single biggest untested readfile surface), grease-pencil v3,
physics/particles/cloth caches, Alembic/USD cache readers, image/movie packing,
library `link`/`append` across real external `.blend`s, and pathological
`invalid_blendfiles/`. These need `git lfs pull` (multi-GB; network + disk not
spent here) and should be layered in once available. Recorded as an open item.

## 3. Dump format (`state_dump.py`, `schema_version: 1`)

Per-file JSON: `{schema_version, quant_scale, source_name, collections}` where
`collections` is a fixed, ordered set of `bpy.data` collections; each holds
`{count, names[sorted], items{name → fingerprint}}`. Items are keyed by name
(library-disambiguated), so **RNA iteration order never reaches the output**.

Per-type fingerprints (structural, meaningful, not superficial):
- **mesh:** vert/edge/loop/poly counts; sha256 of quantized vertex positions;
  hashes of edge/loop/poly topology + per-face `material_index`; full
  `attributes[]` (name/domain/data_type **+ value hash**) — this catches every
  CustomData layer surviving the round-trip; uv/color layer names; material
  slots; shape-key names.
- **object:** type, parent (+bone/type), matrix_basis / matrix_parent_inverse /
  matrix_world (micro-int 4×4), loc/rot/scale, rotation_mode, vertex groups,
  material slots, per-modifier and per-constraint **generic RNA scalar
  snapshot** (`rna_scalars`: writable non-hidden props, pointers→`<id:NAME>`),
  drivers, assigned action.
- **material / world / node_group / scene-compositor:** node graph — per node
  `{type=bl_idname, location, input/output identifiers, unlinked input
  default_values}`, sorted link list `[from,from_sock,to,to_sock]`, node-group
  interface sockets.
- **action:** flattened fcurves (`data_path,array_index,keyframe_count,
  keyframes_hash,extrapolation`) collected from the **5.2 slotted system**
  (`layers[].strips[].channelbags[].fcurves`, legacy `.fcurves` fallback); slot
  count + **slot identifiers** (not `slot_handle`); layer count; frame range.
- **armature:** bones with parent, head_local/tail_local, use_connect/deform,
  matrix_local hash.
- **curve:** rna_type, dimensions, splines (type/point_count/cyclic/order),
  TextCurve body/size/font/align. **light / camera / image / font / text /
  texture / collection / scene:** curated deterministic field sets.

### Determinism contract (why output is byte-stable across builds)
1. **No floats in the JSON.** Every number is `q(x)=round(x·1e6)` → an integer.
   This removes *all* dependence on float `repr`/`printf` — the primary
   wasm-side risk — at the source. Output contains only ints, strings, bools,
   null, arrays, objects.
2. **Everything sorted / keyed by name;** `json.dumps(sort_keys=True)`;
   `ensure_ascii=True`; forced `\n` line endings (no CRLF drift on any host).
3. **Runtime pointer-likes excluded:** `ID.session_uid`, channelbag
   `slot_handle`, addresses. Absolute paths → basename. No timestamps.
4. **Hashing is applied only to verbatim-from-file arrays** (mesh coords,
   topology, attribute data, keyframe coords, bone rest transforms) — these are
   bit-exact reads (no FP recompute), so a hash is safe. **Composed transforms**
   (`matrix_*`) are stored as explicit micro-int arrays, *not* hashed, so the
   comparison tool can apply per-element tolerance if a build ever differs by a
   sub-micro ULP.

## 4. Determinism proof (two independent oracle invocations)

`run_dumps.sh` dumps each file **twice in separate `oracle/bpy.sh` processes**
and asserts byte-identical output before staging. Result: **9/9 PASS, 0 dump
errors.** The `dump_sha256` recorded in `MANIFEST.json` is that twice-verified
hash:

| file | dump sha256 | blend sha256 |
|---|---|---|
| startup | `1692c242c17827cf…` | `1335899143c7e77b…` |
| mesh_dense | `a35eede927a5cb81…` | `54293498822334e4…` |
| modifiers | `179015c3f694fc41…` | `f3569d6f696dcb5f…` |
| animation | `636351c5c4459055…` | `c4eeb78f1300d91f…` |
| materials_nodes | `89087b3b6dbaa05d…` | `73d7eda330a0ffe8…` |
| curves_text | `8e98f222569109c9…` | `e37bf9ef450fe147…` |
| armature | `fc178d44da7ca84d…` | `47a8bde5d5201… ` |
| collections_instancing | `afaacbfa4cd4b191…` | `825897d62f036bef…` |
| stress_mixed | `0bd6f6b9ea0609df…` | `c2a7974ceec3da3e…` |

Full 64-hex digests + sizes in `goldens-candidate/MANIFEST.json`.

### `session_uid` characterization (the pointer-name decision)
Tested `stress_mixed.blend` across two separate invocations: object session_uids
were `161…182`, mesh `183,184` — **identical across the two runs**, i.e.
deterministic *within* a build. **But** the base (161) is the count of IDs the
app allocated during factory-startup before the file load; a different startup
allocation on the wasm build shifts every value. It is therefore **safe within a
build, unsafe across builds → excluded** from the dump. Same reasoning excludes
the channelbag `slot_handle` (`929201142`).

## 5. Comparison tool (`compare_dumps.py`)

Recursive structural diff → first N divergences as JSON paths, tagged
`value`/`hash`/`type`/`list_len`/`only_in_A`/`only_in_B`. Baseline is exact
equality (the tolerance *is* the 1e-6 quantization). Optional `--tolerance N`
loosens numeric-**measurement** leaves by N micro-units while a
`STRUCTURAL_INT_KEYS` allowlist keeps counts/indices/`users`/hashes exact so
tolerance can never mask a real divergence. Keep `--tolerance 0` for the gate.

Self-test (`--selftest`): golden-vs-itself = **PASS (0 divergences)**;
golden-vs-mutated (vertex_count +1, position_hash zeroed, object removed) =
**FAIL** with readable diff → `SELFTEST_PASS`. Cross-file comparison returns
exit 1. Verified.

## 6. Open questions for the wasm side

1. **No Python at M1.** This dump is pure bpy; the wasm runtime gets Python at
   **M2** (`import bpy`). The `.blend`-load-parity gate can only run on wasm
   *after* M2 wires bpy under node — OR an equivalent C++ readfile→JSON dumper
   is written for M1. Flag the sequencing to the driver: this ORACLE side is
   ready now; the wasm side blocks on M2. (The generated `.blend`s exercise the
   pure C readfile paths regardless, so a C++ dumper could reuse this schema.)
2. **Float formatting is *designed out*,** not merely assumed equal — zero
   floats reach the JSON. The residual FP dependency is the *quantization
   rounding* of composed transforms; `matrix_*` are stored (not hashed) so
   `--tolerance` covers a sub-micro ULP without a hash blowout. Verbatim reads
   (coords/topology) are bit-exact and hashed; a hash divergence there would be
   a *real* readfile bug and should fail the gate.
3. **Dict ordering:** dumps never depend on Python dict iteration; keys are
   sorted at serialization. CPython 3.13 dicts are insertion-ordered, but we
   `sort_keys` regardless (belt and braces).
4. **`json.dumps` integer/`sort_keys` behavior** must match between native
   CPython 3.13.13 and wasm CPython 3.13 — same interpreter, expected identical,
   but the wasm-side run should re-verify one file byte-for-byte against these
   goldens before trusting the batch.
5. **Corpus depth:** versioning (`blo_do_versions`) is the largest untested
   readfile surface and needs an LFS pull of `upstream/tests/files` to cover.

## 7. WASM-SIDE RESULTS (2026-08-04) — M1.12 GATE GREEN, closes M1_CORE_BOOTS

Ran `state_dump.py` on the **WASM `blender` build** (node + NODERAWFS; M2.5 boot
recipe — trampoline + fstat shim) over all 9 corpus files, via
`sandbox/corpus-prep/run_dumps_wasm.sh` → `dumps-wasm/`. Each `bpy.ops.wm.open_mainfile`
exercises the real wasm readfile/DNA reconstruction (the corpus was written by the
64-bit oracle; wasm32 reads it — the exact path the driver's DNA fix, patch 0014,
repaired). Compared to the oracle candidate goldens with `compare_dumps.py` in
**EXACT mode (`--tolerance 0`)**.

**Result: 9/9 PASS, all BYTE-IDENTICAL to the oracle goldens** (wasm dump sha256 ==
`MANIFEST.json` `dump_sha256`, not merely structurally equal):

| file | wasm dump sha256 (== oracle golden) | verdict |
|---|---|---|
| startup | `1692c242c17827cf…` | PASS (exact) |
| mesh_dense | `a35eede927a5cb81…` | PASS (exact) |
| modifiers | `179015c3f694fc41…` | PASS (exact) |
| animation | `636351c5c4459055…` | PASS (exact) |
| materials_nodes | `89087b3b6dbaa05d…` | PASS (exact) |
| curves_text | `8e98f222569109c9…` | PASS (exact) |
| armature | `fc178d44da7ca84d…` | PASS (exact) |
| collections_instancing | `afaacbfa4cd4b191…` | PASS (exact) |
| stress_mixed | `0bd6f6b9ea0609df…` | PASS (exact) |

Zero divergences, zero tolerance consumed (gate ran at `--tolerance 0`). No
`_dump_error` in any dump.

**Wasm-side determinism:** `startup.blend` dumped twice in separate node processes →
**byte-identical** (`1692c242c17827cf…`, which also equals the oracle golden). So the
wasm build is deterministic AND matches native — the designed-out-float contract
holds across the toolchains.

**Coverage proven bit-exact on wasm:** the state fingerprints are byte-identical, so
every hashed verbatim-from-file array read the same bits on wasm32 as on the 64-bit
oracle — mesh CustomData (all domains, 15 attrs, UV/byte-color/custom-float/vgroup),
modifier stack + inter-object pointers, slotted actions/fcurves/drivers, shader node
graphs + node group, TextCurve/Bezier/NURBS + VFont, armature rest-pose bones,
collection hierarchy + dupli instancing, 20-user shared mesh + orphans, and the
zstd-decompressed startup baseline. This is genuine 64-bit→wasm32 readfile parity, not
a synthetic-parser check.

### One build fix required to run the gate (not a parity failure)
The FIRST wasm run failed 8/9 with `_dump_error: AttributeError("module 'hashlib' has
no attribute 'sha256'")` — a side effect of M2.5's optional-module trim (state_dump.py
sha256-hashes mesh data). This was NOT a readfile bug (curves_text, which has no mesh
sha256 path, passed byte-identical, and determinism passed). Fix: re-enabled the
`_sha2` CPython module in `scripts/deps/python.sh` (it builds `libHacl_Hash_SHA2.a`,
which the harvest merges cleanly, and provides `hashlib.sha256`; md5/sha1/sha3/blake2
stay off — their Hacl code has no standalone archive). libpython rebuilt; re-run → 9/9
exact. (Bonus: fewer hashlib startup warnings.)

### Open item unchanged
LFS-pulled versioning corpus (`blo_do_versions_*`) remains the biggest untested
readfile surface — layer in post-gate once `git lfs pull` runs.
