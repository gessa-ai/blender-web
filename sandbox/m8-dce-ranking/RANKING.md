<!--
SPDX-FileCopyrightText: 2026 blender-web contributors
SPDX-License-Identifier: CC0-1.0
-->

# M8 DCE ranking - evidence-ranked feature-cut table for the windowed wasm

**Date:** 2026-08-07 · **Author:** M8 size worker (take 2) · emcc **6.0.5** ·
**Measurement-only** (no cmake flips, no rebuilds; analysis of existing artifacts).

## Charter

`notes/m8-wasm-shrink.md` proved the compiler levers (`-Os`/`-Oz`/`--closure`/`-flto`)
are spent: the shipped wasm is already `-O2` + binaryen, and brotli is insensitive to the
instruction-repacking those flags do. Only *removing whole functions/subsystems* moves the
wire. This file ranks the launch-tier-unneeded subsystems by their **real, post-DCE
contribution to the linked wasm** and estimates the brotli-wire impact per cut, so a future
config lane can pick cuts by evidence, not by archive size (which lies).

## Method (two proxies, one real; honest about each)

**Inputs (existing artifacts, read-only):**
- Shipped optimized module `build-wasm-windowed-opt/bin/blender_browser.wasm`
  (`-O2 -g0`; 131,005,926 B; the module whose whole-file brotli is the note's 20.13 MB).
- Debug-info twin `build-wasm-windowed/bin/blender_browser.wasm` (`-O2 -g`; identical
  optimization, plus DWARF). Both retain a wasm `name` section.
- Per-module archives `build-wasm-windowed-opt/lib/libbf_*.a` and deps `lib/wasm/lib/*.a`.

**Method 1 - archive brotli-q5 proxy (coarse, PRE-DCE, overstates).** `wc -c` + `brotli -q 5`
on each `.a`. An archive holds every object the linker *could* pull, plus per-object symbol
tables and relocations; the linker then DCEs most of it. So archive size is an **upper bound
that overstates by 3-5x** (quantified in the exemplar). Useful only for coarse ordering and
for deps that have no clean symbol prefix.

**Method 2 - name-section symbol histogram of the SHIPPED module (real, POST-DCE).** The
decisive lever: the opt module was built `-g0` but **still carries a demangled `name`
section**, so `llvm-nm --print-size --demangle` yields **108,275 sized function symbols with
names** covering **88,706,387 of the 88,706,390-byte CODE section** (99.9997%). Each symbol's
size is its real byte cost *in the shipped binary, after DCE*. A Python classifier
(`classify.py`, ordered regex, specific-before-general) buckets every function by subsystem
using Blender's distinctive C++ namespaces (`blender::seq::`, `blender::compositor::`,
`blender::nodes::node_geo_*`, `blender::*::greasepencil`, `spreadsheet`) and dep prefixes.
This is byte-accurate attribution of the actual wire binary, not a proxy.

**Brotli conversion factor.** CODE section extracted (offset 444,151, 88,706,390 B) and
compressed: **88,706,390 raw -> 15,076,250 brotli-q11 (5.884:1; k = 0.16996 brotli bytes per
raw code byte).** Per-cut wire estimate = `post-DCE raw bytes x k`. This assumes a subsystem
compresses like the code-section average; the exemplar shows self-contained subsystems
compress **worse** than average, so these estimates are **conservative (a lower bound on the
saving)**. Cross-check: code 15.08 + name 1.04 (below) + wasm-DATA ~4.0 = ~20.1 MB, matching
the note's measured 20.13 MB whole-module brotli.

## Exemplar - sequencer/VSE done properly (all three methods on one cut)

Chosen because the VSE is the cleanest self-contained subsystem (own `blender::seq::`
namespace + `space_sequencer` editor).

| method | measurement | value | what it means |
|---|---|---|---|
| M1 archive proxy (pre-DCE) | `libbf_sequencer.a` raw / brotli-q5 | 2,418,250 B / **832,841 B** | overstates: includes DCE'd objects + reloc/symtab |
| M2 shipped-binary attribution (post-DCE) | 718 functions, summed sizes | **771,617 B raw** | real code kept in the wire |
| M2 -> wire, average factor | 771,617 x k | **131,139 B br** | conservative estimate |
| M2 -> wire, **actual** | extract the 718 funcs' bytes, brotli-q11 | **187,188 B br** | true standalone compressibility |

Readings:
- **The archive proxy overstates the real cut by 4.4x** (832,841 vs 187,188). Never rank cuts
  by archive size.
- The **actual** standalone brotli (187 KB) is **1.43x the average-factor estimate** (131 KB):
  the VSE's leaf code compresses at 4.12:1 versus the code-section average 5.88:1, because
  concatenated non-contiguous functions lose the cross-function redundancy a whole-module
  brotli window exploits. So the average-factor column below is conservative; realistic
  per-cut savings are ~1.2-1.5x higher.
- Caveat on "actual": 187 KB is the subsystem compressed *alone*; the true **marginal** wire
  saving from removing it (whole-module brotli with vs without) is slightly less, because some
  of its dictionary is shared with retained code. The real number sits between the two M2
  columns, i.e. **~0.13-0.19 MB brotli for the whole VSE.**

## The ranking (post-DCE, from the shipped opt module)

Sorted by realizable brotli-wire impact. "Realizable?" flags whether a stock toggle exists.

| # | subsystem | funcs | post-DCE raw | raw MiB | est. wire (xk) | realizable via |
|---|---|---:|---:|---:|---:|---|
| A | **shader compiler** (shaderc+glslang+SPIRV-Tools+Tint) | 7,966 | 5,726,363 | 5.46 | **~973 KB** | **JSPI split**, not cut (needed to compile shaders) |
| B | **geometry nodes (ALL families)** | 4,266 | 6,102,959 | 5.82 | ~1,037 KB | no toggle; only non-mesh subset is a candidate and it is **not cleanly separable** (see risks) |
| C | **sculpt/paint** (bonus; not on the brief list) | 2,909 | 3,960,499 | 3.78 | **~673 KB** | new WITH_ guard; **not launch-tier** |
| D | **compositor** (CPU + realtime + `nodes/composite`) | 1,431 | 1,994,407 | 1.90 | ~339 KB | new patch guard (no stock flag) |
| E | **grease pencil** (v3 + legacy, editor+core) | 1,785 | 1,836,032 | 1.75 | ~312 KB | new patch guard (no stock flag) |
| F | **sequencer / VSE** | 718 | 771,617 | 0.74 | ~131 KB (actual **~187 KB**) | new patch guard (no stock flag) |
| G | editor space: spreadsheet | 315 | 266,093 | 0.25 | ~45 KB | guard `add_subdirectory(space_spreadsheet)` |
| H | editor: NLA | 285 | 188,569 | 0.18 | ~32 KB | patch (interwoven with animation) |
| I | editor space: clip/tracking (residual) | 125 | 106,642 | 0.10 | ~18 KB | mostly already gone (WITH_LIBMV OFF); only UI stubs remain |
| - | Cycles | 0 | 0 | 0 | 0 | **already OFF** (WITH_CYCLES) |
| - | libmv / motion tracking | ~1 | ~0 | 0 | 0 | **already OFF** (WITH_LIBMV) |
| - | OpenVDB / volumes backend | 0 | 0 | 0 | 0 | **already OFF** (WITH_OPENVDB) |
| - | OIIO non-essential formats | - | see below | - | <~100 KB | JPEG2000/WebP/Cineon **already OFF**; residual needs a deps rebuild |

Deps for context (mostly NOT cuttable; mandatory for launch tier):

| dep | funcs | post-DCE raw | raw MiB | est. wire | note |
|---|---:|---:|---:|---:|---|
| CPython (partial attribution) | 9,379 | 6,515,277 | 6.21 | ~1,107 KB | **mandatory** (Python UI + bpy); real total higher (many CPython symbols lack a Py prefix) |
| OpenColorIO | 5,435 | 3,424,878 | 3.27 | ~582 KB | launch-tier colormanagement (AgX view transform) |
| OpenImageIO | 2,853 | 2,188,755 | 2.09 | ~372 KB | launch-tier image IO; format trim below |
| numpy | 1,143 | 1,432,618 | 1.37 | ~243 KB | pulled by addons (glTF); split candidate |
| TBB | 1,238 | 1,093,569 | 1.04 | ~186 KB | mandatory (threading) |
| freetype | 795 | 567,606 | 0.54 | ~96 KB | mandatory (UI text) |

Whole-binary buckets (blenlib 18.99, rna 7.62, bke 6.09, ed-other 5.84, gpu 3.04, draw 1.17,
bmesh 0.51 MiB) are launch-tier core and are floored, not candidates. `blenlib` is
over-attributed by a greedy catch-all rule and mixes generic C++/templates; it is not a cut.

## OIIO non-essential formats - largely already done

Blender's image layer already forces `WITH_IMAGE_OPENJPEG=OFF`, `WITH_IMAGE_WEBP=OFF`,
`WITH_IMAGE_CINEON=OFF` (`patches/blender_web.cmake:189-191`), so the imbuf readers for those
are out. What remains is OIIO's **own** built-in format plugins (TIFF via `libtiff` 628 KB
archive, etc.), which are compiled into `libOpenImageIO.a`, not gated by a Blender flag.
Trimming them means rebuilding OIIO in the deps superbuild (`scripts/deps/`) with a reduced
format set (keep PNG/EXR/JPEG), not a WITH_* flip. Estimated ceiling well under ~100 KB
brotli after DCE. **Low priority.**

## Top-5 recommended actions for a future config lane (DO NOT FLIP - recommendation only)

Reality check first: the biggest feature candidates (compositor, VSE, grease pencil, geometry
nodes, editor spaces) have **no stock `WITH_*` toggle** - upstream adds them unconditionally
via `add_subdirectory()` (`upstream/source/blender/CMakeLists.txt:145,151`;
`.../editors/CMakeLists.txt:18,46,47`). Cutting them needs a new blender-web patch that guards
those `add_subdirectory()` calls behind blender-web options AND stubs the WM/RNA/DNA
registration that references them. The stock flags that *do* exist (Cycles, libmv, OpenVDB,
image formats) are **already OFF**. So the ranked recommendations below mix one flag-free
link-time action with four new-patch compile-outs, ordered by (brotli win x safety):

1. **Strip the wasm `name` section** - link `-sno-name-section` (or post-link `wasm-opt
   --strip-debug --strip-producers` / `llvm-strip`). **~1.04 MB brotli, ZERO feature risk, no
   patch.** Measured: the shipped module still ships a 20,381,645 B raw name section that
   compresses to **1,092,933 B** of pure symbol-name debug metadata. This lever was never
   tested by the compiler-lever probe and is the single largest safe wasm cut available today.
   (Keep a symbolicated build for stack traces off the critical path.)
2. **Compile out sculpt/paint** (new `WITH_BLENDER_WEB_SCULPT=OFF` guard). **~0.67 MB
   brotli.** Sculpt mode is not in the launch tier (modeling/edit-mode/modifiers are). Biggest
   safe *feature* compile-out. Risk: shared brush/paint DNA and some `BKE_paint` used by
   texture paint and vertex color; audit RNA/DNA references.
3. **Compile out the compositor** (guard `add_subdirectory(compositor)`, `compositor/shaders`,
   `nodes/composite`, and the space_node compositor path). **~0.34 MB brotli.** Not launch-tier
   (workbench+EEVEE viewport does not need the compositor). Risk: node-tree RNA registration,
   scene DNA `bNodeTree` compositor pointers, `.blend` files that carry compositor trees.
4. **Compile out grease pencil** (v3 + legacy: editor `grease_pencil`, core
   `bke::greasepencil`, `io/grease_pencil`). **~0.31 MB brotli.** Not launch-tier. Risk:
   highest of the set - GP has DNA (`GreasePencil`, legacy `bGPdata`), RNA, modifiers, and
   `.blend` back-compat; a partial cut can break file load. Cut whole or not at all.
5. **Compile out the VSE + spreadsheet/clip/nla editor spaces as one bundle** (guard
   `sequencer`, `space_sequencer`, `space_spreadsheet`, and trim `space_clip`/NLA UI).
   **~0.29 MB brotli combined** (VSE ~0.19 actual + spreadsheet ~0.05 + nla ~0.03 + clip
   ~0.02). Lowest-risk feature cuts (leaf UI spaces), smallest per-cut win.

**Bigger than all five compile-outs combined - the structural lever:**
**JSPI-split the shader compiler** (item A: shaderc+glslang+SPIRV-Tools+Tint, 5.46 MiB raw,
**~0.97 MB and realistically ~1.3-1.4 MB brotli**). It is needed to translate BSL/GLSL ->
SPIR-V -> WGSL, but **not at boot** if the shader library is precompiled to WGSL and served
from OPFS cache (the note's own M3 disk-cache plan). Lazy-load it as a secondary module after
first pixels, exactly the Doom-3 pattern already applied to `.data`. This single split removes
more boot-wasm brotli than every compile-out on the list together.

## Honest method caveats

- **Archive size != post-DCE linked size.** Demonstrated on the VSE exemplar: 832,841 B
  archive brotli vs 187,188 B real. All Method-1 numbers overstate 3-5x. Rank by Method 2.
- **Average-factor wire estimates are conservative.** The exemplar shows a self-contained cut
  compresses ~1.4x worse than the code average, so realized savings run higher than the xk
  column; but the true **marginal** saving is slightly below the standalone-brotli number
  because of shared dictionary. The real per-cut value sits between the two, and only a
  rebuild-and-recompress measures it exactly (out of scope for measurement-only).
- **Debug-vs-opt is NOT a caveat here** - attribution is on the shipped `-O2 -g0` module
  directly (its retained name section), so per-function sizes are the real wire bytes.
- **Geometry nodes (item B) is a poor compile-out despite its size:** the launch tier needs
  "geometry nodes (mesh)", and the mesh vs non-mesh families (points, volume/grid, curves,
  simulation/xpbd) live in one library and share declaration/field/socket infrastructure. No
  toggle isolates them; a per-node-file exclusion is fragile and the realizable subset is a
  fraction of the 5.82 MiB. **Not recommended as a compile-out; revisit only under a
  node-registry split.**
- CPython attribution is a lower bound (many interpreter symbols lack a `Py` prefix); it is
  not a candidate anyway (mandatory), so precision there was not pursued.
- Brotli factor derived from one whole-code-section q11 measurement; brotli is content
  dependent, so treat all wire numbers as +/- ~20%.

## Reproduce

```
NM=tools/emsdk/upstream/bin/llvm-nm
$NM --print-size --demangle build-wasm-windowed-opt/bin/blender_browser.wasm > nm_opt.txt
python3 classify.py nm_opt.txt                 # the ranking table
python3 exemplar.py nm_opt.txt                 # extract seq/VSE bytes -> seq_bytes.bin
brotli -q 11 -c seq_bytes.bin | wc -c          # 187,188 (actual VSE brotli)
# code-section factor:
tail -c +444152 build-wasm-windowed-opt/bin/blender_browser.wasm | head -c 88706390 \
  | brotli -q 11 -c | wc -c                     # 15,076,250
# name-section strip lever:
tail -c 20381645 build-wasm-windowed-opt/bin/blender_browser.wasm | brotli -q 11 -c | wc -c  # 1,092,933
```

`classify.py` and `exemplar.py` are archived alongside this file.
