<!--
SPDX-FileCopyrightText: 2026 blender-web contributors
SPDX-License-Identifier: CC0-1.0
-->

# m2b divergence root-cause: `bl_node_copy_operators` ungroup socket → `NodeSocketUndefined`

Follow-up to notes/m2-tierb-prep.md §6/§6a ("node-socket type undefined (1)"). Disposition:
**DEEPER (node-system + threading heisenbug) — STOP, no patch. Not a documented port class.**

## Symptom (reproduced)

`sandbox/tierb-prep/run_suite_wasm.sh bl_node_copy_operators` → `FAILED (failures=4)`.
All 4 are in `test_ungroup` / case `test_ungroup_proxy_nodes`, socket name `"Value"`:
`bl_node_copy_operators.py:426` `assertEqual(test_socket.bl_idname, …)` →
`'NodeSocketUndefined' != 'NodeSocketFloat'` (×4). (First reproduction this session; raw log had
the 4 identical assertions, 0 bhead/corruption lines.)

## It is NON-DETERMINISTIC (~1.4%), no controllable trigger

Measured this session: **1 failure in ~70 runs**. The one failure was the session's very first
`blender.js` exec (cold). Every attempt to force it AGAIN failed to reproduce:
- 40 sequential warm runs: 0 fail.
- Parallel (6-wide × 3 rounds): 0 socket-fails (but exposed a *separate* real bug — see below).
- 15 runs under 20× CPU oversubscription (preemption jitter): 0 fail (5 completed in the window).
- 4 runs after evicting the 103 MB `.wasm` from page cache (30 GB touch): 0 fail.

So "cold start" was not the cause — run #1 was just the base-rate flake landing first. The prior
worker (m2-tierb-prep.md §6) also saw it during a *warm* 75-suite run, consistent with a genuine
low-rate flake, not a deterministic divergence.

## Localized (deterministic, via oracle dump of the full stateful sequence)

The failing `"Value"` sockets are the **output sockets of `ShaderNodeValue` proxy nodes**
(the run's trees contain 40 such proxies, named `Value`…`Value.039`; each output `"Value"` is
`NodeSocketFloat`). The `test_ungroup_proxy_nodes` case's ungroup creates 4 of them and, in the one
failing run, **all 4 went `Undefined` together** — a per-*operation* transient, not per-socket.

Creation path (a Float group-interface input with a constant value / no incoming link needs a
constant proxy on ungroup):
- `node.group_ungroup` → `node_group_ungroup` — `editors/space_node/node_group.cc:255,274`
- → `connect_copied_nodes_to_external_sockets` — `editors/space_node/node_copy_util.cc:1090`
- → `replace_interface_socket` → `create_proxy_const_input_node` — `node_copy_util.cc:1034`
- → `bke::node_interface::create_proxy_const_input_node`, **SOCK_FLOAT** branch —
  `blenkernel/intern/node_tree_interface.cc:1607-1615`:
  `bNode *node = bke::node_add_node(&C, dst_tree, "ShaderNodeValue"); … outputs.first` — the output
  `"Value"` socket is the one that intermittently ends up with `typeinfo == &NodeSocketTypeUndefined`.

## Ruled out (with evidence)

- **NOT node/socket registration / static-init / dead-strip.** Directly adding `ShaderNodeValue`
  to a `GeometryNodeTree` yields `out0.bl_idname == NodeSocketFloat` **deterministically on BOTH the
  native oracle AND wasm** (repro: scratchpad `repro_sock.py`). `"NodeSocketFloat"` and
  `"ShaderNodeValue"` are registered and resolve fine. A dead-strip/static-init-order bug would be
  deterministic (always Undefined), which this is not.
- **NOT the `.blend` readfile/bhead-collision family** (the *other* node bug,
  `bl_node_structure_type_inference`). `NodeSetCopy` copies nodes with the **in-memory**
  `bke::node_copy_with_mapping` (`node_copy_util.cc:718`), not `.blend` partial-write
  serialization; the failing run's log has **0** bhead lines.
- **NOT payload / ILP32 / libc.** No missing data; deterministic on the same ILP32 build for the
  direct-add path.

## Mechanism (leading hypothesis; not fully proven — why STOP)

`bl_idname == "NodeSocketUndefined"` ⟺ `sock->typeinfo == &NodeSocketTypeUndefined`, set by
`node_socket_set_typeinfo(ntree, sock, nullptr)` (`blenkernel/intern/node.cc:2677-2679`) when the
caller's `node_socket_type_find(sock->idname)` returned `nullptr`
(`node.cc:2729/2732` in `node_tree_set_type`, run during the post-ungroup tree update).
`node_socket_type_find` (`node.cc:2939`) reads a **function-local `static` VectorSet**
(`get_socket_type_map()`, `node.cc:2764`) that is **read-only after boot**. For a lookup of the
static name `"NodeSocketFloat"` to miss, a transient/scheduling-sensitive condition must hold — the
classic signature of a **data race or an uninitialized read** in the threaded wasm profile
(`-sPROXY_TO_PTHREAD` + TBB; m2-python-boot.md). Two candidates, not yet separated:
1. **Race**: the ungroup mutates a `bNodeTree` that is *also* a GN modifier's `node_group` on
   `TestObject`; each loop iteration flushes a depsgraph update → GN evaluation may run on TBB
   workers concurrently with the next operator's tree mutation (typeinfo writes + topology-cache
   rebuild). If copy-on-eval isolation is imperfect on wasm, worker/main share the tree.
2. **Uninitialized read** of a freed-then-reused `bNodeSocket` field (`idname`/typeinfo) — wasm
   fresh linear memory returns zeros early, stale bytes later, which fits "rare + all proxies of one
   operation fail together" (same reused region).

Both are node-system/threading-architecture issues, **not a one-line port-class fix** — hence STOP
per the task gate. `--debug-memory` (guardedalloc) did not make it deterministic (15+ passes), which
neither confirms nor refutes uninitialized-read (it guards overruns, not new-alloc contents).

## Secondary real bug found (file separately — not this gate)

Under concurrent execution the test's own `bpy.ops.node.clipboard_copy()`
(`bl_node_copy_operators.py:292`) **aborts**:
`BLI_assert failed: editors/space_node/clipboard.cc:241, node_clipboard_copy_exec(), at '0'`
("marked unreachable") because `copy_buffer.write_as_copypaste_buffer(...)` (`clipboard.cc:240`)
returns false — multiple processes collide on the **shared** copybuffer temp path
(`node_copybuffer_filepath_get`, `clipboard.cc:48`). Harmless for the *sequential* m2b gate, but a
real hazard for any concurrent/multi-context wasm (browser multi-tab) build and worth a per-context
copybuffer path. (This is why my parallel stress showed `rc=1` without a `FAILED` unittest line.)

## Recommended next step for the driver (bounded)

One instrumented build (node source is pristine at the pin — no patch touches `node.cc` /
`space_node/`, so a temp probe reverts cleanly). Probe both:
(a) `create_proxy_const_input_node` SOCK_FLOAT, immediately after `node_add_node` — is
`socket->typeinfo` already the Undefined type? (→ creation-time vs later-clear);
(b) `node_socket_set_typeinfo` else-branch — log `sock->idname` bytes + `pthread_self()` + an
immediate re-`node_socket_type_find(sock->idname)` (succeeds now ⇒ **race**; still null ⇒ idname
garbage ⇒ **uninitialized read**).
Then a background hunt of ~150 runs (to clear the ~1.4% rate with confidence). I judged this not
worth burning in THIS iteration: single-run capture probability is marginal and the STOP disposition
(it is deep) is already determined. If the probe shows the race, the fix is copy-on-eval / tree-lock
isolation; if uninitialized, zero-init the reused socket field.

## Reproduce

```
sandbox/tierb-prep/run_suite_wasm.sh bl_node_copy_operators   # ~1.4% FAIL; mostly OK
# direct-add control (both PASS: NodeSocketFloat):
oracle/bpy.sh --python <repro_sock.py>
BLENDER_SYSTEM_RESOURCES=upstream BLENDER_SYSTEM_PYTHON=lib/wasm \
  BLENDER_SYSTEM_DATAFILES=upstream/release/datafiles \
  tools/emsdk/node/22.16.0_64bit/bin/node build-wasm/bin/blender.js \
  --background --factory-startup --python <repro_sock.py>
```
Node-type dump of the failing sockets (oracle, full stateful sequence): all `ShaderNodeValue`
output `"Value"` = `NodeSocketFloat`. upstream left pristine (HEAD fbe6228, node sources untouched);
no rebuild done.
