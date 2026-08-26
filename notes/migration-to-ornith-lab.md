# Migration runbook: ornith-lab (WSL2 Ubuntu, RTX 4090)

<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

This is the cold-start authority for reconstructing the repository at
`/home/pc/gessa/blender-web`. Only the outer `.git` directory is transferred. Do not expect any
macOS checkout, tool, dependency harvest, build tree, browser installation, OPFS profile, or
temporary evidence directory to exist.

## 1. Truth at the handoff

- Branch at the start of migration work: `agent/m2.5-python-boot`; old base HEAD `7090add`.
  Migration commits are on that same branch and are the source of truth after transfer.
- Blender pin: `fbe6228777e7d9afefcd61a413844e790ae75db7`, branch
  `blender-v5.2-release`.
- Emsdk repository: `1ab2e627b1a84567f5284d1baaa5f6be7ccf07de`; SDK 6.0.5 release
  `dbd755b5da399329c2576f6e3dfa7f419f5d8409`; emcc compiler
  `1db513782be24469589d7cb8a1f1834e9a33f271`; emsdk Node `v22.16.0`.
- Dawn/Tint pin: `36cf1fae0cd8a81a4fb4580751648b80b2e6255c` (`chromium/7989`).
- Recorded host tools were CMake 4.0.3, Ninja 1.13.1, Apple clang 17.0.0, Python 3.13.13
  for working Dawn codegen, and glslangValidator 16.4.0. On Linux use CMake 4.0.3,
  Ninja 1.13.1, clang/lld 17, Python 3 with working `pyexpat`, and glslang 16.4.0 where
  available. The Wasm compiler identity comes from emsdk and must match exactly even if the
  Linux host compiler package has a different patch build.
- Playwright package: 1.61.1. Install its own Linux Chromium; never point the M4 gate at the old
  macOS cache.
- Native comparison oracle: Blender 5.2.0 at the same source pin and oiiotool 2.4.17.0, provided
  reproducibly by `containers/oracle/Dockerfile`.

The immutable accepted M4 evidence is the 2026-08-09 D-9 run in
`sandbox/m4-d9-gate/evidence/final-receipt.txt`: splash 1,882 pixels / 0.204%, workspace 4,653
pixels / 0.505%, both over threshold 0.016 and below failpercent 1. The later
`ledger/results/m4.json` is RED because newer JS/Wasm/data bytes no longer match a later binding.
That RED is honest. A Linux build needs a new label and receipt.

## 2. Restore the worktree and exact Blender source

After the transferred `.git` has been placed in the empty target directory, check out the branch
normally. Then reconstruct the ignored upstream tree:

```bash
cd /home/pc/gessa/blender-web
git status --short
bash scripts/bootstrap.sh
git -C upstream rev-parse HEAD
# Must print fbe6228777e7d9afefcd61a413844e790ae75db7.

(cd patches && sha256sum -c PREVIEW_SNAPSHOT.sha256)
git -C upstream apply --check ../patches/PREVIEW_SNAPSHOT.patch
git -C upstream apply ../patches/PREVIEW_SNAPSHOT.patch
git -C upstream apply --reverse --check ../patches/PREVIEW_SNAPSHOT.patch
.host-tools/bin/python3.13 sandbox/series-replay/verify.py
```

`patches/canonical` names this single squashed source-reconstruction patch. The historical
filename is retained because the stronger canonical freezer regenerated the file byte-for-byte;
renaming or duplicating the 1.5 MB blob would add no integrity. Its SHA-256 is
`42fd53158a55c78a3e8c8ba9a3014dbf505c931302d652620bdee704ab3b15fd`. It is the exact
integration-tree authority, including 257 concrete modified/untracked upstream paths (210 in
Git's compact status view). Do not reconstruct the current tree by applying an arbitrary subset
of numbered historical patches.

The shared checkout also contained tracked outer-repository changes owned by other lanes. They
were not folded into this agent's commit. They are preserved byte-for-byte in
`patches/OUTER_WORKTREE_REMAINDER.patch`, SHA-256
`5c96c94fb14cd91e87e6ad3493301856894d05fdcc24656267140a16f0175708`. Apply it once after
checking out the migration commit:

```bash
(cd patches && sha256sum -c OUTER_WORKTREE_REMAINDER.sha256)
git apply --check patches/OUTER_WORKTREE_REMAINDER.patch
git apply patches/OUTER_WORKTREE_REMAINDER.patch
```

This patch is the shared-worktree preservation mechanism, not an assertion that all contained
lanes are independently green. Review and split it into owner commits after the first exact
reconstruction; do not lose it during onboarding.

The Blender Linux precompiled dependency gitlink at this source pin is exact commit
`30d9f881c4b62c52323fd11637eeea56d460e35c`:

```bash
git clone https://projects.blender.org/blender/lib-linux_x64.git lib/linux_x64
git -C lib/linux_x64 checkout --detach 30d9f881c4b62c52323fd11637eeea56d460e35c
git -C lib/linux_x64 lfs pull
git -C lib/linux_x64 lfs fsck
```

The explicit LFS pull is required even when `git-lfs` was installed before the clone: a cold
checkout can otherwise retain pointer text at the correct commit, which is not detected until a
native link reports that a dependency library has an unrecognized file format. `lfs fsck` must
report `Git LFS fsck OK` before configuring a native build.

`lib/macos_arm64` is not copied and has no Linux use.

## 3. Install host tools

Ubuntu package names vary by release; these are the required capabilities. Keep the recorded
versions where commands below pin them instead of silently using newer tools.

```bash
sudo apt-get update
sudo apt-get install -y \
  build-essential git git-lfs curl ca-certificates xz-utils unzip zip \
  python3 python3-venv python3-pip ccache pkg-config perl \
  autoconf automake libtool meson nasm yasm \
  clang-17 lld-17 glslang-tools \
  libegl-dev zlib1g-dev libzstd-dev \
  libx11-dev libxrandr-dev libxinerama-dev libxcursor-dev libxi-dev \
  libwayland-dev wayland-protocols libxkbcommon-dev \
  libvulkan-dev vulkan-tools mesa-vulkan-drivers

python3 -m venv .host-tools
. .host-tools/bin/activate
python -m pip install --upgrade pip
python -m pip install 'cmake==4.0.3' 'ninja==1.13.1'
/usr/bin/python3 -m venv .host-tools/reuse-6.2.0
.host-tools/reuse-6.2.0/bin/python -m pip install 'reuse==6.2.0'
cmake --version
ninja --version
clang-17 --version
.host-tools/reuse-6.2.0/bin/reuse --version
```

The M8 technical-compliance producer requires that exact REUSE executable. Export
`BW_REUSE_BIN="$PWD/.host-tools/reuse-6.2.0/bin/reuse"`; a different version, a relative path,
or a symlinked executable fails before a receipt is allocated.

For the browser rig, install native Node 22.16.0 (for `npm`) using the site's standard Node
manager or the official Linux x64 archive. Do not substitute emsdk's Node path for an npm
installation, although both runtimes should report 22.16.0.

Docker Desktop's WSL integration or a native Docker Engine must be enabled for the pinned oracle:

```bash
bash scripts/oracle-container.sh verify
```

## 4. Install the exact Emscripten SDK

`tools/` is ignored and must be rebuilt:

```bash
mkdir -p tools
git clone https://github.com/emscripten-core/emsdk.git tools/emsdk
git -C tools/emsdk checkout --detach 1ab2e627b1a84567f5284d1baaa5f6be7ccf07de
tools/emsdk/emsdk install 6.0.5
tools/emsdk/emsdk activate 6.0.5
source tools/emsdk/emsdk_env.sh
emcc --version
"$EMSDK_NODE" --version
```

The first lines must contain emcc `6.0.5
(1db513782be24469589d7cb8a1f1834e9a33f271)` and Node `v22.16.0`. Then run the non-receipt
toolchain proof:

```bash
EM_CACHE=$PWD/.ci-cache/emscripten \
CCACHE_DIR=$PWD/.ci-cache/ccache \
bash scripts/ci/m0-basic.sh
```

## 5. Rebuild `lib/wasm` (do not transfer `lib/`)

`lib/` is 2.7 GB of generated, platform-specific dependency state. It is now ignored in full.
`lib/wasm` must be rebuilt from the committed, idempotent recipes. Use one emsdk shell and the
global build wrapper. The order below is explicit; several recipes also enforce their own
prerequisites.

```bash
source tools/emsdk/emsdk_env.sh
export CC=emcc CXX=em++ AR=emar RANLIB=emranlib

deps=(
  zlib zstd fmt eigen robinmap imath libdeflate openjph
  openexr libjpeg libpng libtiff expat yamlcpp pystring minizipng
  opencolorio brotli freetype tbb openimageio
  tint shaderc python wheels numpy opensubdiv openusd
)
for dep in "${deps[@]}"; do
  harness/buildwrap.sh bash "scripts/deps/${dep}.sh" || exit 1
done

# The dependency loop intentionally leaves CXX=em++. Host-only code generators
# must use the recorded native compiler after their fmt/zstd headers are harvested.
harness/buildwrap.sh env CXX=clang++-17 bash scripts/build-hosttools.sh
harness/buildwrap.sh bash scripts/build-locale-datafiles.sh
```

All archives, headers, Python 3.13.13 stdlib/site-packages, shaderc/Tint order manifests,
OpenSubdiv GLSL source, and OpenUSD core land under `lib/wasm`. Native `datatoc`, `shader_tool`,
and `msgfmt` plus the compiled locale catalogs land under `build-hosttools/`. `build-deps/` is
scratch and may be discarded after successful harvest. Do not copy the macOS harvest or relink
any macOS archive.

## 6. Rebuild the M4 windowed Wasm product (CAPTURE phase)

The shipping M4/M5 artifact is an APPLY-mode primary/deferred pair. A cold checkout cannot
reproduce that pair in one link: APPLY is accepted only with two strict browser profiles bound to
the exact new Linux `.wasm.orig`. Start in CAPTURE mode; never substitute an OFF-mode monolith or
copy a profile from the old machine.

Use the canonical configure with paths naturally rooted at the Linux checkout:

```bash
source tools/emsdk/emsdk_env.sh
export EMSDK_PYTHON="$PWD/.host-tools/bin/python3.13"
export CCACHE_DIR="$PWD/.ci-cache/ccache"
export EM_CACHE="$PWD/.ci-cache/emscripten"

BLENDER_WEB_WINDOWED=1 cmake -S upstream -B build-wasm-windowed-opt -G Ninja \
  -C patches/blender_web.cmake \
  -DCMAKE_TOOLCHAIN_FILE="$PWD/tools/emsdk/upstream/emscripten/cmake/Modules/Platform/Emscripten.cmake" \
  -DCMAKE_BUILD_TYPE=Release \
  -DWITH_BLENDER_WEB_BROWSER=ON \
  -DBLENDER_WEB_WASM_SPLIT_MODE=CAPTURE \
  -DCMAKE_EXE_LINKER_FLAGS=-g0

harness/buildwrap.sh scripts/ninja-locked.sh \
  -C build-wasm-windowed-opt blender_browser
scripts/ninja-locked.sh -C build-wasm-windowed-opt -n blender_browser
.host-tools/bin/python3.13 scripts/windowed-product-preflight.py --expect capture
```

The prior cache had `WITH_WEBGPU_BACKEND=ON`, `WITH_PYTHON=ON`,
`WITH_INTERNATIONAL=ON`, `WITH_OPENSUBDIV=ON`, `WITH_CYCLES=ON`, Release/Ninja, and the emsdk
toolchain. Check those values in the new `CMakeCache.txt`. The CAPTURE-phase output set is:

```text
build-wasm-windowed-opt/bin/blender_browser.js
build-wasm-windowed-opt/bin/blender_browser.wasm       # instrumented, non-shipping
build-wasm-windowed-opt/bin/blender_browser.wasm.orig  # exact APPLY input
build-wasm-windowed-opt/bin/blender_browser.data
build-wasm-windowed-opt/bin/blender_browser.split-build.json
```

No deferred shard exists yet. `windowed-product-preflight.py` must report `mode=CAPTURE`; its
default APPLY check must remain blocked at this point. An OFF-mode build emits only JS + monolithic
Wasm + data and is a developer artifact, not an M4 product. Do not reuse the old artifact hashes:
Linux host paths and the current source snapshot require a fresh binding even when generated Wasm
is otherwise deterministic.

## 7. Reproduce the M4 gate under WSLg

Install Playwright into an ignored repo-local prefix and keep its browser cache local. This
replaces both the old `NODE_PATH=/Users/paws/plushly/game-platform/node_modules` and
`~/Library/Caches/ms-playwright` assumptions:

```bash
mkdir -p .m4-node .m4-browsers
npm install --prefix .m4-node --no-save \
  @playwright/test@1.61.1 pngjs@7.0.0 sharp@0.35.3
PLAYWRIGHT_BROWSERS_PATH="$PWD/.m4-browsers" \
  "$PWD/.m4-node/node_modules/.bin/playwright" install chromium

export BW_NODE_MODULES="$PWD/.m4-node/node_modules"
export PLAYWRIGHT_BROWSERS_PATH="$PWD/.m4-browsers"
export BLENDER_WEB_BIN="$PWD/build-wasm-windowed-opt/bin"
```

Do not produce a CAPTURE profile on llvmpipe or another software/fallback adapter. First satisfy
the hardware-adapter acceptance in `notes/wsl-vulkan-investigation-20260819.md`, including the
Chromium-side adapter proof. A software run is useful only for diagnosis and binds no profile,
split product, or M4 receipt.

With the accepted adapter, serve the CAPTURE build on port 8165 and collect both required
controller scenarios under distinct immutable labels:

```bash
BLENDER_WEB_BIN="$PWD/build-wasm-windowed-opt/bin" bash scripts/serve-web.sh 8165

# In a second shell with BW_NODE_MODULES, PLAYWRIGHT_BROWSERS_PATH, and
# BLENDER_WEB_BIN exported as above:
profile_root="$PWD/sandbox/m8-wasm-split/profile-evidence"
node22="$PWD/tools/emsdk/node/22.16.0_64bit/bin/node"
"$node22" sandbox/m8-wasm-split/capture_blender_profile.mjs --selfcheck
"$node22" sandbox/m8-wasm-split/capture_blender_profile.mjs \
  --port 8165 --threads 1 --scenario success --run ornith-linux-success-r1
"$node22" sandbox/m8-wasm-split/capture_blender_profile.mjs \
  --port 8165 --threads 1 --scenario terminal-error --run ornith-linux-terminal-r1

orig_sha="$(sha256sum build-wasm-windowed-opt/bin/blender_browser.wasm.orig | awk '{print $1}')"
.host-tools/bin/python3.13 sandbox/m8-wasm-split/merge_profiles.py \
  --output "$profile_root/ornith-linux-union-r1.data" \
  --capture-receipt "$profile_root/ornith-linux-success-r1/receipt.json" \
  --capture-receipt "$profile_root/ornith-linux-terminal-r1/receipt.json" \
  --expected-orig-sha256 "$orig_sha" \
  "$profile_root/ornith-linux-success-r1/profile-hot.data" \
  "$profile_root/ornith-linux-terminal-r1/profile-hot.data"
```

The producer itself is the final s7 guard: before allocating either immutable run directory it
requires exact Node 22.16.0, Playwright 1.61.1 with bundled Chromium 149.0.7827.55, PNGJS 7.0.0,
Linux WebGPU launch arguments, and a browser-reported non-fallback adapter with non-empty identity
data. It rejects llvmpipe,
lavapipe, softpipe, SwiftShader, WARP, CPU/software renderers, and masked adapter information.
Both the profile union and APPLY finalizer independently recheck that exact adapter/tool receipt;
an internally inconsistent edit or old-schema macOS capture cannot authorize a Linux shard.

Stop the server before relinking. Convert the same build tree to APPLY using only that exact
profile union and its generated receipt, then build through the global lock:

```bash
.host-tools/bin/cmake -S upstream -B build-wasm-windowed-opt \
  -DBLENDER_WEB_WASM_SPLIT_MODE=APPLY \
  -DBLENDER_WEB_WASM_SPLIT_PROFILE="$profile_root/ornith-linux-union-r1.data" \
  -DBLENDER_WEB_WASM_SPLIT_PROFILE_RECEIPT="$profile_root/ornith-linux-union-r1.data.receipt.json" \
  -DBLENDER_WEB_WASM_SPLIT_ORIG_SHA256="$orig_sha"
harness/buildwrap.sh scripts/ninja-locked.sh \
  -C build-wasm-windowed-opt blender_browser
scripts/ninja-locked.sh -C build-wasm-windowed-opt -n blender_browser
.host-tools/bin/python3.13 scripts/windowed-product-preflight.py --expect apply
```

The final shipping set is JS, primary Wasm, deferred Wasm, and data. The APPLY build also retains
the exact `.wasm.orig` and `blender_browser.split-build.json` as build evidence. The preflight
rejects missing, stale, symlinked, extra, or receipt-mismatched Wasm artifacts before any M4 label
is allocated.

WSL must expose a headed WSLg session (`DISPLAY` or `WAYLAND_DISPLAY`) and the browser must obtain
a hardware WebGPU adapter backed by the RTX 4090. A software adapter is not an equivalent replay.
The capture driver intentionally launches headed Chromium and requires DPR 1 and an exact
1280x720 backing/CSS canvas.

Start the COOP/COEP server in one terminal:

```bash
BLENDER_WEB_BIN="$PWD/build-wasm-windowed-opt/bin" \
  bash scripts/serve-web.sh 8141
```

In another terminal, choose a never-used immutable label:

```bash
export BW_NODE_MODULES="$PWD/.m4-node/node_modules"
export PLAYWRIGHT_BROWSERS_PATH="$PWD/.m4-browsers"
export BLENDER_WEB_BIN="$PWD/build-wasm-windowed-opt/bin"
run=m4-ornith-r1

node sandbox/m4-d9-gate/capture_m4.mjs splash 8141 "$run"
node sandbox/m4-d9-gate/capture_m4.mjs workspace 8141 "$run"
python3 sandbox/m4-d9-gate/bind_current.py --run "$run"
M4_BINDING="sandbox/m4-d9-gate/evidence/${run}.binding.json" \
  python3 sandbox/m4-d9-gate/verify_current_binding.py
M4_BINDING="sandbox/m4-d9-gate/evidence/${run}.binding.json" \
  bash harness/run.sh --scope m4
```

The verifier hashes all four product artifacts, six served shell files, both captures/receipts,
the tracked native goldens, and the gate sources; it then reruns the unchanged
`oiiotool --fail 0.016 --failpercent 1 --diff` comparator. Set `OIIOTOOL` to a Linux executable
reporting 2.4.17.0 if it is not on `PATH`. Do not regenerate the tracked macOS-native goldens on
Linux: different window/font stacks would change the oracle rather than reproduce it.

## 8. Native M3/Dawn rebuild on Linux

This is required before new GPU translation work, but not to run the M4 Wasm capture. Clone Dawn
and its exact pin:

```bash
git clone https://dawn.googlesource.com/dawn build-dawn/dawn
git -C build-dawn/dawn checkout --detach 36cf1fae0cd8a81a4fb4580751648b80b2e6255c
```

The committed `sandbox/dawn-probe/CMakeLists.txt` and `build.sh` still force the macOS shape
(`DAWN_ENABLE_METAL=ON`, Vulkan OFF, `CMAKE_OSX_DEPLOYMENT_TARGET=11.2`). Before running them on
Linux, make one bounded portability change: select Metal+11.2 only on APPLE and select Vulkan ON,
Metal OFF on Linux. Keep the Dawn/Tint pin and all other build options identical. This is an
explicit migration blocker, not permission to update Dawn.

After the Vulkan probe passes on the RTX 4090, configure the native gate with Linux libraries,
the generated Dawn include directory and Linux `libwebgpu_dawn.a`. The former macOS cache contract
must translate as follows:

```text
Release + Ninja
WITH_WEBGPU_BACKEND=ON
WITH_VULKAN_BACKEND=OFF       # Blender backend under test remains WebGPU
WITH_METAL_BACKEND=OFF
WITH_GPU_DRAW_TESTS=ON
WITH_OPENSUBDIV=ON
WITH_CYCLES=OFF
LIBDIR=<repo>/lib/linux_x64
DAWN_INCLUDE_DIRS=<dawn>/include;<probe-build>/dawn/gen/include
DAWN_LIBRARIES=<probe-build>/dawn/src/dawn/native/libwebgpu_dawn.a plus its Linux link closure
```

Do not paste the old Apple framework list (`Cocoa`, `CoreGraphics`, `Foundation`, `IOKit`,
`IOSurface`, `Metal`, `QuartzCore`) into Linux. Let Dawn's CMake target or its generated Linux
link manifest provide Vulkan/X11/system libraries. Then build only through the lock:

```bash
harness/buildwrap.sh scripts/ninja-locked.sh -C build-native-gpu blender_test bf_io_usd
scripts/ninja-locked.sh -C build-native-gpu -n blender_test bf_io_usd
python3 sandbox/final-m0-m3/run_m3.py --help
```

Before issuing a receipt, reproduce exact 197/197, DrawWebGPU 2/2, and the exact 1,003
cold-MISS/warm-HIT contract recorded in `notes/gpu-r26-migration-savepoint.md`.

## 9. macOS assumptions and Linux equivalents

| Old assumption | Linux/WSL equivalent or disposition |
|---|---|
| `/Users/paws/blender-web` in M4, current M5 click-pick/canvas-smoke/ROI-latency, current M6 Workbench/EEVEE capture, the current M7 USD and files-browser producers, the current M8 staged capture, and its staged assembly/server/update support | Removed; JavaScript roots derive from `import.meta.url`, Python from `__file__`, and shell assembly from `BASH_SOURCE[0]`. Retained historical rigs remain immutable. |
| `NODE_PATH=/Users/paws/plushly/game-platform/node_modules` | M4, current M5 click-pick/canvas-smoke/ROI-latency, current M6 producers, the current M7 USD and files-browser producers, and the M8 product/performance/soak/staged producers use `BW_NODE_MODULES=$PWD/.m4-node/node_modules`; Playwright 1.61.1, PNGJS 7.0.0, and host-only Sharp 0.35.3 install into that local prefix for the accepted-adapter replay. The latency producer also binds libvips 8.18.3. |
| `~/Library/Caches/ms-playwright` and macOS `.app` bundle | `PLAYWRIGHT_BROWSERS_PATH=$PWD/.m4-browsers`; install Playwright's Linux Chromium. |
| `/opt/homebrew/bin/cmake`, Ninja, Python, glslang | Pinned venv CMake/Ninja plus Ubuntu clang/Python/glslang commands above. |
| Apple clang 17 and `CMAKE_OSX_DEPLOYMENT_TARGET=11.2` | clang/lld 17; remove the OSX deployment flag. |
| Dawn Metal device and Apple framework link closure | Dawn Vulkan on the WSL2 RTX 4090; regenerate the Linux link closure. |
| `lib/macos_arm64` | Exact `lib/linux_x64` gitlink commit plus rebuilt `lib/wasm`. |
| `oracle/blender-5.2.0/Blender.app/Contents/MacOS/Blender` | Prefer `scripts/oracle-container.sh`; for `oracle/bpy.sh`, set `BLENDER_BIN` to a verified Linux Blender 5.2.0 executable. |
| Native golden capture uses a visible macOS Blender window | Do not regenerate for M4 replay. Use tracked goldens. A future Linux golden campaign is a new adapter baseline. |
| `codesign`, `spctl`, `CFBundleIdentifier`, plist versions in M7/M8 | Not part of M4. The M7 Firefox/Safari contract self-check is host-independent, but its strict real Safari row remains a macOS capture and still rechecks Apple signatures. For Linux-native browser rows in later gates, replace these fields with canonical ELF path/hash plus distro package signature/version checks; do not weaken by marking the macOS fields true. |
| `.m8-browsers/Google Chrome.app`, `Microsoft Edge.app`, signed geckodriver | Not transferred. The current M8 Chrome+Edge matrix, 30-second product producer, pinned performance producer, 30-minute soak, and staged capture verify canonical Linux package ELFs through exact `dpkg`/APT/keyring identities; performance and soak also select the Linux stable-release feed. Install instructions and paths are in `sandbox/m8-launch-gate/README.md`. Their live rows still wait on s7/APPLY; the M7 Safari row remains macOS-only. |
| `/tmp/blender-web-ninja.lock` | `/tmp` exists in WSL; current lock script works unchanged. |
| `date`, `mktemp`, `stat`, `sed`, Bash behavior in `harness/` | GNU variants satisfy current scripts. `harness/buildwrap.sh`, `harness/run.sh`, and `scripts/serve-web.sh` have no remaining macOS absolute path. |
| macOS free-space behavior and browser Metal caches | Recheck with `df -h`; all build/browser caches remain disposable and ignored. |

## 10. What the Git transfer does and does not preserve

Preserved in commits: port source snapshot, patch history, gate programs, canonical identity
manifests, goldens, selected immutable M4 receipts, ledger state, decisions, and this runbook.

Rebuild/download: `upstream/`, `tools/emsdk`, `lib/`, `build-deps/`, `build-dawn/`, native and
Wasm build trees, Docker images, Node packages, Playwright browsers, `.m8-browsers`, profiles,
OPFS/cache state, and ignored diagnostic evidence.

The initial untracked inventory was 2,760 file paths (Git's collapsed status showed 511 entries).
Bulk screenshots, logs, browser profiles, Wasm probes and repeated evidence trees were classified
as reproducible spill and ignored. Programs, configs, legal texts, fixtures, canonical manifests,
and the selected M4 evidence were committed. `lib/` is explicitly rebuild-only, not source.

## 11. First cold-agent checklist

1. Read `GOAL.md`, `notes/decisions.md`, `fix_plan.md` M3/M4, ADRs,
   `notes/gpu-r26-migration-savepoint.md`, then this file.
2. Run `harness/status.sh` only after checking out the migration commits; expect historical RED
   rows until new receipts exist.
3. Verify the canonical patch SHA, reconstruct upstream, and run the canonical replayer.
4. Install exact emsdk and run `scripts/ci/m0-basic.sh`.
5. Rebuild `lib/wasm`, windowed Wasm, and M4 browser dependencies.
6. Reproduce M4 with a fresh label. Stop on a software adapter, artifact mismatch, missing
   deferred Wasm, non-DPR1 capture, GPU validation error, or comparator RED.
7. Only then port/rebuild native Dawn Vulkan and resume GPU translation work.
