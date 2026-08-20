<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M5 trusted click-pick continuation receipt

This headed Playwright gate drives two real, trusted canvas click-select cycles
through the shipping windowed shell. A read-only Python timer reports the
VIEW_3D projection and observes selection state; it does not invoke an operator
or write selection state. Each cycle deselects with trusted `Alt+A`, clicks the
projected center of the default cube, and requires the unchanged native
`object_click_select` operator sequence.

The driver fails closed on a missing/extra `view3d.select`, untrusted DOM input,
wrong final state, browser/GPU error, crash, external request, wrong canvas
geometry, or an existing evidence label.

The repository root is derived from the driver. Playwright resolves from
`BW_NODE_MODULES`, each `NODE_PATH` entry, `.m4-node/node_modules`, then the
repository's `node_modules`, and must be the pinned 1.61.1 package. Evidence is
confined to one immutable child of a repository-local output root. `--selfcheck`
validates those contracts without opening a browser or reading a build product.

Before launching the browser it binds exactly the shipping JS, primary Wasm,
deferred Wasm, and data files. The split manifest must classify only the
primary and deferred Wasm files as shipping; `.wasm.orig`, split maps, and the
manifest itself are retained only as build/provenance inputs.

```sh
node sandbox/m5-click-pick/drive-click-pick.mjs --selfcheck

export BW_NODE_MODULES="$PWD/.m4-node/node_modules"
export PLAYWRIGHT_BROWSERS_PATH="$PWD/.m4-browsers"
export BLENDER_WEB_BIN="$PWD/build-wasm-windowed-opt/bin"

bash scripts/serve-web.sh 8166

node sandbox/m5-click-pick/drive-click-pick.mjs \
  --port 8166 --run m5-click-pick-r3

python3 sandbox/m5-click-pick/verify-click-pick.py
```

A real receipt requires the s7-accepted hardware WebGPU adapter and an APPLY
split product. The self-check is the only supported invocation before that
gate; a software adapter binds no M5 evidence.
