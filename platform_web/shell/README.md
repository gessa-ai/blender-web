<!--
SPDX-FileCopyrightText: 2026 blender-web contributors
SPDX-License-Identifier: GPL-2.0-or-later
-->

# blender-web browser shells (local link)

The canonical local server exposes the windowed native-app product shell at `/`.
The earlier headless M4.pre diagnostic remains available explicitly at
`/index.html`, or as the root page with `BLENDER_WEB_ENTRY=index.html`.

## 1. Serve the windowed product (COOP/COEP required)

```sh
BLENDER_WEB_BIN="$PWD/build-wasm-windowed-opt/bin" scripts/serve-web.sh
BLENDER_WEB_BIN="$PWD/build-wasm-windowed-opt/bin" scripts/serve-web.sh 8123
```

The server sets `Cross-Origin-Opener-Policy: same-origin` and
`Cross-Origin-Embedder-Policy: require-corp` on every response — mandatory, because
threads ⇒ SharedArrayBuffer ⇒ cross-origin isolation. Opening the files with a plain
static server (or `file://`) will **not** work.

## 2. Open the windowed product in Chrome / Edge

Navigate to the printed URL (for example, `http://localhost:8123/`). The native-app
shell boots immediately and is the same source page installed as `/index.html` by
the production bundle assembler.

## 3. Run the legacy headless diagnostic

The legacy page runs the Wasm build with `--background --factory-startup`. It is
the browser equivalent of the Node boot in `notes/m2-python-boot.md`; its design
and verification are recorded in `notes/m4-browser-shell.md`.

Build that browser binary once:

```sh
cd <repo-root>
cmake build-wasm -DWITH_BLENDER_WEB_BROWSER=ON
scripts/ninja-locked.sh -C build-wasm blender_browser
```

This produces `build-wasm/bin/blender_browser.{js,wasm,data}`. The `.data` file
contains the preloaded CPython standard library, Blender scripts, and datafiles.

Start the server with the headless build and explicit legacy entry:

```sh
BLENDER_WEB_BIN="$PWD/build-wasm/bin" BLENDER_WEB_ENTRY=index.html \
  scripts/serve-web.sh 8123
```

Navigate to the printed URL (e.g. `http://localhost:8123/`) in **current Chrome or
Edge**, then click **Boot Blender**. stdout/stderr stream to both the on-page log box
and the devtools console (F12). The status bar shows state / exit code / wall time.

To change the arguments, edit the single `ARGV` array at the top of `boot.js` (the
`--python-expr` there prints `BPY_OK <version> <#objects>` once Python boots).

## Expected output (GREEN — full headless boot)

The DNA reconstruct fix has landed, so the tab now boots Blender all the way through
`import bpy` and exits cleanly:

```
Blender 5.2.0 LTS
BPY_OK 5.2.0 LTS 3
Blender quit
```

`3` = objects in the factory startup scene (cube, camera, light). The page state pill
turns **exited (0)** and the exit code is `0` (wall ~1.6 s for boot + import).

You will also see benign noise that does NOT stop the boot:
- one OpenImageIO wasm stub before the banner:
  `... sysutil.cpp:214: physical_memory: Assertion ... failed.`;
- Python `Traceback`s / `ModuleNotFoundError: No module named '_multiprocessing'`
  and unsupported `sha3`/`shake` hashes — optional C extensions disabled in the
  libpython harvest; the affected add-ons (e.g. `bl_pkg`) fail to register and
  Blender continues. `import bpy` still succeeds → `BPY_OK` → exit 0.

### Runtime env (important)

The shell sets `BLENDER_SYSTEM_RESOURCES=/bw` in `boot.js` (the ONE place, in
`ENV_VARS`). This is what makes `import bpy` resolve: Blender's scripts folder-id
reads the umbrella `BLENDER_SYSTEM_RESOURCES` base and looks for
`<base>/scripts/modules` (appdir.cc:712 → get_path_system_ex:568) — it does NOT read
a `BLENDER_SYSTEM_SCRIPTS` env of its own. The preload mounts scripts/datafiles/
python under `/bw`, so `/bw` is the base.

## Notes / limits

- Dev-grade eager preload (one big `.data`). Staged/lazy loading + stdlib
  tree-shaking + OPFS project store are M7 (`LAUNCH.md`) — see
  `notes/m4-browser-shell.md`.
- Headless (`--background`). No WebGPU canvas yet (that is M3/M4 proper); this shell
  proves boot + Python parity, not pixels.
- `blender_browser` is `EXCLUDE_FROM_ALL` and gated on `-DWITH_BLENDER_WEB_BROWSER=ON`,
  so it never affects the node / gtest iteration builds.
