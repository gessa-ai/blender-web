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

Before launching the browser it binds exactly the shipping JS, primary Wasm,
deferred Wasm, and data files. The split manifest must classify only the
primary and deferred Wasm files as shipping; `.wasm.orig`, split maps, and the
manifest itself are retained only as build/provenance inputs.

```sh
BLENDER_WEB_BIN=/Users/paws/blender-web/build-wasm-windowed-opt/bin \
  /Users/paws/blender-web/scripts/serve-web.sh 8166

BLENDER_WEB_BIN=/Users/paws/blender-web/build-wasm-windowed-opt/bin \
  node /Users/paws/blender-web/sandbox/m5-click-pick/drive-click-pick.mjs \
  --port 8166 --run m5-click-pick-r3

python3 /Users/paws/blender-web/sandbox/m5-click-pick/verify-click-pick.py
```
