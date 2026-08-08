<!--
SPDX-FileCopyrightText: 2026 blender-web contributors
SPDX-License-Identifier: CC0-1.0
-->

# LAUNCH.md close-out audit (M8 deploy-prep lane)

**Date:** 2026-08-08 · **Author:** M8 deploy-prep worker · repo HEAD `5750083`
(branch `agent/m2.5-python-boot`, at/after `fbfb31d`) · **prepare-only** (no
deploy, no public push, no name choice).

This is the map the driver drives the launch close-out from: every LAUNCH.md box
scored **DONE** (with receipt), **IN-FLIGHT** (which lane owns it), **OPEN** (what
it still needs), or **HUMAN** (a decision only a person may take - the D-7 public
name, the lawyer skim, the post itself, the AI-authorship history call).

## Scoreboard

| bucket | count | boxes |
|---|---:|---|
| **DONE**      | 2  | L3, L8 |
| **IN-FLIGHT** | 6  | L4, L5, S2, S5, O1, O2 |
| **OPEN**      | 9  | I2, L6, L7, S1, S3, S4, S6, O3, and the launch-site content cluster |
| **HUMAN**     | 3  | I1, L9, S7 |
| **total**     | 20 | (2 identity + 7 license + 8 thirty-second-bar + 3 proof-artifact) |

Box IDs below: **I**=identity, **L**=license/attribution, **S**=the 30-second bar,
**O**=proof artifacts. They are in LAUNCH.md order.

## Top blockers (headline, worst first)

1. **Wasm wire size - the hard gate.** The wasm module alone is **20.13 MB
   brotli (19.19 MiB) - 34% over the 15 MB "to-interactive" bar before one byte of
   data.** Stage-0 wire-to-interactive is **24.71 MB (1.6x over)**. Compiler levers
   are spent (`-Os`/`-Oz`/`--closure`/`-flto` move it <1%, and the two "size" levers
   move the *wire* the wrong way). Only source-level feature-DCE + a JSPI wasm-split
   close it. Gates **S1** and the whole staged-load promise. Owner: config lane
   (`patches/blender_web.cmake`) + a JSPI-split lane. Math + evidence in the last
   section.
2. **Solid-cube render (GPU Bug B).** The workbench opaque group's GPU-driven
   `DrawIndexedIndirect` produces no fragments (gbuffer depth stays 1.0 at the cube),
   so the default cube is not solid. This lane's own boot capture rendered **black on
   the current in-flight r29 binary** (splash and workspace alike, one present then
   idle). Gates the wow-shot **S4**, fidelity **S5**, and the survivable demo **O1**.
   Owner: gpu-backend lane (r29 in flight; last VERIFIED render was r28b-take3
   `aaf51f2` - grid/outline/menus up, cube not solid).
3. **AI `Co-authored-by` in git history (box L7) - RED, reputational.** Every recent
   commit carries `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>` (verified
   `git log`, HEAD..HEAD~8 all have it). LAUNCH.md L7, D-7, and GOAL.md all say
   **human author + `Assisted-by:` only, NO AI `Co-authored-by`** - because Blender's
   contributor policy bans AI commit authorship and this is the exact fight LAUNCH.md
   warns not to re-detonate. HUMAN decision: strip via history filter before the
   public repo is cut, or revise the policy. Do not leave it latent.
4. **Public name undecided (box I1, D-7) - HUMAN.** Blocks repo/domain/handle name,
   the app `<title>` (currently the local working name), the disclaimer wording, and
   the entire post. Nothing publishes until it is chosen.
5. **Staged loading + service-worker not integrated.** Proven as mechanisms
   (`notes/m8-staged-loading.md`: monolith wire 47.5 -> 23.6 MiB, lazy-fetch works)
   but the shipping shell still monolith-loads via `--preload-file`; SW precache is
   absent. Gates **S1**.
6. **Launch-site content absent:** root `README.md`, footer "Source code (GPL)"
   link, the proof-of-native UI line, `?scene=` share URLs, hosted conformance
   dashboard, methodology writeup, `AUTHORS` file. Individually small, collectively a
   lane. Several are HUMAN-worded (they carry the name/framing).

---

## I - Repo/product identity

### I1 - Own brand, "Blender" never leads, no Blender logo -- HUMAN
The public name is undecided and human-owned (D-7; `notes/decisions.md:116`). The
local working name `blender-web` appears in the shell `<title>` and source comments
and MUST be swapped at publish. No Blender logo ships anywhere: the bundle has **no
favicon by design** (a favicon is brand art = a naming decision), and the shell
carries none. Nominative-use scaffolding is already correct in `NOTICE`
("used here only descriptively/nominatively"). **Needs:** a chosen brand, then a
mechanical substitution pass across shell title/comments/repo metadata.

### I2 - Standing disclaimer in README, site footer, repo description -- OPEN
The disclaimer text exists verbatim in `NOTICE:25-28` ("NOT affiliated with,
endorsed by, or sponsored by... Blender(R) is a registered trademark..."). But there
is **no root `README.md`**, the native-window shell has **no footer**, and the repo
description is a publish-time step. **Needs:** README + a footer surface (or an
About panel) + repo description, all carrying the disclaimer; wording depends on I1.

---

## L - License & attribution (day-one, CI-enforced)

### L3 - Aggregate GPL-3.0-or-later; derived GPL-2.0-or-later; texts in LICENSES/ -- DONE
`LICENSES/` carries `GPL-3.0-or-later.txt`, `GPL-2.0-or-later.txt`, `Apache-2.0.txt`
(Cycles-derived), `CC0-1.0.txt` (docs/config). Aggregate posture stated in `NOTICE`
and `PROVENANCE.md`. Receipt: `ls LICENSES/`; `reuse lint` reports exactly these four
as the used-license set with **0 bad / 0 deprecated / 0 invalid SPDX expressions**.

### L4 - Per-file SPDX + provenance; PROVENANCE.md maps modules -- IN-FLIGHT
`PROVENANCE.md` defines the per-file header convention (upstream copyright verbatim +
ours + SPDX id + one `Ported for the web from <path> @ fbe6228777e7` line) and a
module map. The map is still mostly "planned" rows (gpu/webgpu, ghost web,
platform_web). Per-file SPDX **is** applied across the tracked source set (see L6).
Owner: compliance lane. **Needs:** fill the module map as modules land.

### L5 - NOTICE/AUTHORS + THIRD-PARTY.md -- IN-FLIGHT
`NOTICE` credits "Blender Authors" and "Blender Foundation" as origin (correct).
`THIRD-PARTY.md` lists every runtime dep (CPython, oneTBB, OpenEXR, OpenImageIO,
OpenColorIO, zlib, FreeType, libepoxy) with license + GPL-compat=yes, but every row
is marked **"pending"** (not yet reconciled to shipped) and the canonical record is
`ledger/deps.json`. **`AUTHORS` file is MISSING at repo root.** **Needs:** add
`AUTHORS`; flip THIRD-PARTY rows pending -> shipped with versions/URLs.

### L6 - reuse lint green + app footer "Source code (GPL)" link -- OPEN
**reuse is green on the tracked source set (what CI lints), red on this dev
worktree.** Bare `reuse lint` here returns **exit 1** only because it scans
**untracked build trees** - `build-wasm-windowed-opt/`, `build-wasm-windowed/`,
`build-wasm-gpu/`, `build-wasm-cycles/` (~30k copied Blender datafiles/shaders with
no SPDX) - plus untracked r29 debug PNGs under `platform_web/shell/evidence/`. These
are a **`.gitignore` gap**: `build-wasm/` is ignored but the `-windowed*/-gpu/-cycles`
variants are not, so they are neither committed nor skipped. A fresh CI checkout has
no build trees, so CI sees the tracked set green (tracked non-`upstream` files = 1001;
reuse counts 1080 files with copyright info).
- **Real tracked gaps (only 2 files):** `platform_web/shell/evidence/m4-r24-final-black-1280x720.png`
  and `.../m4-r24-r23code-black-1280x720.png` lack SPDX (committed evidence PNGs; not
  this lane's files).
- **App footer "Source code (GPL)" link: does NOT exist** (no footer surface; shell
  is a chrome-less native window).
**Needs:** (a) gitignore the `build-wasm-*` variants (config/harness lane, not this
one); (b) SPDX-annotate the 2 tracked PNGs (shell lane); (c) build the footer/About
Source-link (depends on I1). Verdict: **fix the gitignore gap so the local lint
matches CI, then this is a near-DONE tracked-set green.**

### L7 - Human author, Assisted-by trailers, NO AI Co-authored-by -- OPEN (RED) / HUMAN
Author config is human (`KA <25724612+ka-rar@users.noreply.github.com>`) and
`Assisted-by:` trailers are present - **but every recent commit ALSO carries
`Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`**, which L7 explicitly
forbids. This is a live, pervasive history violation, not a one-off. **HUMAN
decision** (blocker #3 above): strip AI co-authorship from history before cutting the
public repo, or change the stated policy. Flag before it is inherited by the public
mirror.

### L8 - Server-side Blender-derived code -> AGPL (else GPL) -- DONE (N/A)
The port is **pure client-side** (WASM + WebGPU in the tab; the deploy bundle is a
static host with no server logic - see `_headers`, no functions). No Blender-derived
code runs server-side, so GPL suffices and AGPL is not triggered. **Keep this true:**
if any Blender-derived code ever moves server-side, L8 re-arms.

### L9 - GPL-literate lawyer skims license posture + final post wording -- HUMAN
External review, pre-launch. Not started (nothing to review until the post + name
exist). HUMAN-owned.

---

## S - The 30-second bar (M8 gates on this)

### S1 - Staged load: <=15 MB / cube in <=5-8 s + real progress UI + SW precache -- OPEN
- **Progress UI: partial DONE.** The shell shows a phased indicator with a real MB
  counter driven off Emscripten `setStatus` (`boot-windowed.js:200-234`) - not a bare
  spinner - and dismisses on first `presentBackbuffer`.
- **<=15 MB / <=5-8 s: NOT met.** Wire-to-interactive is 24.71 MB brotli (1.6x over);
  see the wire-math section. The shell still monolith-loads (`--preload-file` baked
  `.data`); staged loading is proven (`notes/m8-staged-loading.md`) but **not
  integrated**.
- **Service-worker precache: NOT implemented.**
Owner: config/DCE lane (wasm size) + a staged-loading integration lane + a SW lane.

### S2 - First interaction proves local: MMB orbit, Tab->edit->extrude -- IN-FLIGHT
M5 proved select / G,R,S with axis constraints / Tab edit-mode / extrude via
event-simulate with operator-trace + state parity (**7/8 byte-exact**, ledger
`4d826ab`/`cbcae67`). Browser-level drive works through this shell. **Gap:** the
"zero-latency / frame-instant" **input-latency budget is unmeasured** (M5 note: "do
not promise yet"). Owner: M5 lane. Also depends on Bug B for a visible orbit.

### S3 - Proof-of-native: explicit line, offline test, quiet network, .wasm in Sources -- OPEN
Technically true and observable now: the bundle runs entirely on-device, my verify
saw the network go quiet after load, and `blender_browser.wasm` is a plain Source.
But the **explicit UI line** ("Runs entirely on your device...") and the **invited
disconnect-your-network** copy are launch-site/shell content **not built**. Owner:
launch-site lane (wording HUMAN-adjacent).

### S4 - Wow moment <=30 s: orbit Classroom (CC0) or drag-drop own .blend -- OPEN
`.blend` open + drag-drop is M7 (open/save proven, `8394b99`/`9cc9f1e`). But: (a) the
Classroom CC0 scene is **not wired** as a `?scene=` preload; (b) the viewport render
is **blocked by Bug B** (cube not solid), so there is no capturable wow-shot yet.
Owner: gpu lane (Bug B) + a scene-preload lane.

### S5 - Fidelity tells in 10 s: splash, cube+camera+light, theme, fonts, keymap -- IN-FLIGHT
Splash arm + `--factory-startup` (default cube/camera/light, Layout workspace) + theme
are wired (M4); keymap validated in M5. **Gap:** Bug B (solid cube) + my capture
rendered black on the in-flight r29 binary. Owner: gpu lane. Last VERIFIED visual:
r28b-take3 (`aaf51f2`) had grid/outline/menus up.

### S6 - Shareable state: ?scene=classroom URLs -- OPEN
Not implemented. The shell has `?gate=`, `?pyexpr=`, `?args=` dev hooks only
(`boot-windowed.js:84-130`). Owner: shell lane. Depends on S4 scene assets.

### O1(ops) / S-ops - Static host + CDN for the hug-of-death; desktop-first, mobile caveats -- IN-FLIGHT
**This lane delivers the static-host artifact:** `make_bundle.sh` assembles a
Cloudflare-Pages-style bundle with a COOP/COEP/CORP `_headers` file, verified to boot
crossOriginIsolated locally (see the boot-verdict section of `README.md`). CDN sizing
for the hug-of-death and the "desktop-first, mobile limitations up front" copy are
launch-time/HUMAN. Owner: this deploy-prep lane (artifact) + launch-site (copy).

### S7 - Post mechanics (lead MP4, numbered thread, Show HN, Tue-Thu AM) -- HUMAN
Content, sequencing, and timing. HUMAN-owned (D-8; LAUNCH.md "The post").

---

## O - Proof artifacts the post links to

### O1 - Live demo surviving the skeptic's path (open->edit->modifier->material->animate->render->save) -- OPEN
Pieces exist per-milestone (M5 edit/transform, M7 save/export) but are **not
assembled into one deployed, no-dead-ends demo**. Blocked on render (Bug B), deploy
(this lane's bundle, + hosting = HUMAN), and name (I1). Owner: driver integration.

### O2 - Live conformance dashboard (per-suite %, vs 5.2.0, deferral registry) -- IN-FLIGHT
`reports/dashboard.md` exists (static markdown, per-suite %) and `ledger/deferred.json`
is the deferral registry with named blockers (Cycles-final, OSL, Mantaflow, >16 GB
Memory64). **Gap:** not HOSTED live. Owner: dashboard/harness lane.

### O3 - Methodology writeup (how the fleet worked; the AI story, with receipts) -- OPEN
Not written. This is where the AI-builder story lives (one click deep, per D-8).
Owner: HUMAN-reviewed writeup lane.

### The post (§ prose) -- HUMAN
Naming/framing rules (lead with the artifact + GPL story, not "AI rewrote Blender";
no mark in taglines; native-not-streamed axis) are HUMAN-owned per D-8. Recorded here
so the driver does not improvise them.

---

## The 30-second bar, explicitly (task requirement)

Restating the eight S-boxes as the demo-packaging gate, with a one-word state:

| # | 30-second-bar item | state |
|---|---|---|
| S1 | staged load, cube in <=5-8 s, <=15 MB, real progress UI, SW precache | **OPEN** (progress UI partial; size + SW not met) |
| S2 | first interaction proves local (MMB orbit, Tab->extrude) | **IN-FLIGHT** (parity proven; latency unmeasured) |
| S3 | proof-of-native line + offline test + quiet network + .wasm visible | **OPEN** (true, but UI copy unbuilt) |
| S4 | wow moment <=30 s (Classroom / drag-drop .blend) | **OPEN** (blocked on Bug B + scene wiring) |
| S5 | fidelity tells in 10 s (splash/cube/theme/keymap) | **IN-FLIGHT** (wired; blocked on Bug B) |
| S6 | shareable `?scene=` URLs | **OPEN** (not implemented) |
| S7 | ops: static host + CDN, desktop-first, mobile caveats | **IN-FLIGHT** (this bundle is the host artifact) |
| S8 | post mechanics (MP4, thread, Show HN, timing) | **HUMAN** |

---

## Honest wire-size math vs the 15 MB bar

Authoritative source: `sandbox/m8-dce-ranking/RANKING.md`,
`notes/m8-staged-loading.md`, `notes/m8-wasm-shrink.md` (all brotli = brotli-q11;
MiB = 2^20, MB = 10^6). A live re-measure was attempted on the current build but the
r29 lane was **relinking the binary mid-read** (raw wasm shifted 123.27 -> 122.80 MB
between reads; the resulting brotli ratio was nonsensical), so the stable RANKING
measurement is cited as authoritative. The current on-disk raw wasm (~123 MB) is in
the same class as RANKING's measured 131 MB module, so the conclusion holds.

| component | brotli | note |
|---|---:|---|
| wasm alone (opt `-O2 -g0`) | **20.13 MB** (19.19 MiB) | **already 1.34x over the 15 MB bar by itself** |
| stage-0 data | 4.50 MB (4.29 MiB) | already trimmed (dedup + dropped `__pycache__`/pip wheels) |
| js glue | ~0.09 MB | closure-minified (live re-measure of js: 77 KB, consistent) |
| **wire-to-interactive (stage-0)** | **24.71 MB** (23.57 MiB) | **1.6x over the bar** |
| monolith today (no staging) | 49.82 MB (47.51 MiB) | 3.2x over |
| stage-1 (lazy, deferred) | ~24.6 MB (23.5 MiB) | off the critical path (proven lazy-fetch) |

**To clear 15 MB with the 4.50 MB stage-0 data (+0.09 js), the wasm must fall to
<=~10.4 MB brotli - a 48% cut.** Compiler levers cannot do it:
- `-Os`/`-Oz`/`--closure`/`-flto` together move the wasm brotli **<1%**, and `-Os`/`-Oz`
  make the *wire* **worse** (binaryen size passes cut raw bytes brotli was already
  deduplicating). Compiler levers are spent as a class.
- Only removing whole functions/subsystems (feature-DCE) or lazy-splitting them
  (JSPI) moves brotli. RANKING's ranked, post-DCE safe cuts:
  name-section strip **~1.04 MB** (zero feature risk, no patch), sculpt/paint
  **~0.67**, compositor **~0.34**, grease pencil **~0.31**, VSE+spreadsheet+clip+nla
  bundle **~0.29** (~**2.65 MB** combined) + the structural lever **JSPI-split the
  shader compiler ~0.97-1.4 MB**. Even summed (~4 MB) the wasm lands ~16 MB - still
  over - so reaching <=10.4 MB additionally requires a **broader JSPI wasm-split**
  (importers/exporters, compositor, sculpt, Cycles as post-first-pixels modules), per
  `notes/m8-wasm-shrink.md` step 2. Data staging (done) + feature-cut + wasm-split are
  all three required; no single lever clears the bar.

---

## What this lane delivered (and what staged-loading will change)

Delivered (prepare-only, all under `sandbox/m8-deploy/`):
- `make_bundle.sh` - assembles the static bundle from the gate build (shell as
  `index.html` + `boot-windowed.js` + `bin/blender_browser.{js,wasm,data}`) with the
  COOP/COEP/CORP `_headers`; symlink by default, `--copy` for a self-contained upload.
- `_headers` - Cloudflare-Pages COOP/COEP/CORP + MIME + cache (committed template).
- `serve_bundle.py` - COOP/COEP static server (port 8130) mirroring the `_headers`.
- `verify_boot.mjs` - headed-Playwright boot -> `crossOriginIsolated` assert -> WM_main
  -> present -> capture. **Boot verdict: PASS** (isolated, WM_main in 829 ms, present
  path executed; captured frame is black on the current in-flight r29 binary - a GPU
  lane state, not a bundle fault - see `README.md`).

**What staged-loading integration (S1) will change here later:** today `bin/` is a
monolith - one `.wasm` + one `--preload-file` `.data` fetched whole. Staged loading
will (a) split `.data` into a boot-critical stage-0 (~21.6 MiB raw / 4.29 MiB brotli)
served first and stage-1 lazy-fetched into cache after first pixels; (b) after the
DCE/JSPI work, split the wasm into a boot module + lazy secondary modules; (c) add a
service worker for precache so a reload is near-instant; (d) introduce content-hashed
filenames so the `_headers` `Cache-Control` can flip to `immutable` long-max-age on
`bin/*`. `make_bundle.sh` and `_headers` are structured so those become additive
changes (new stage manifests + hashed names + a `/sw.js` rule), not a rewrite.
