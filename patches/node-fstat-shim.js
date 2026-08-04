// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: GPL-2.0-or-later
//
// blender-web node runtime pre-run shim (M2.5) — work around an emscripten
// NODEFS.fstat bug that only bites the NODERAWFS (headless node) build.
//
// THE BUG (emscripten, node-only): NODEFS.fstat computes
//     getattr = stream.stream_ops?.getattr ?? stream.node.node_ops?.getattr;
// It guards `node_ops` with `?.` but NOT `stream.node` itself. NODERAWFS's
// createStandardStreams() creates fd 0/1/2 as {nfd, position, path, flags, seekable}
// with NO virtual `node` and NO `stream_ops`, so any fstat() on a standard stream
// throws "Cannot read properties of undefined (reading 'node_ops')" instead of
// falling through to the intended `return fs.fstatSync(stream.nfd)`. CPython does
// exactly this — it fstat()s fd 0/1/2 during interpreter init to probe stdio — so
// the headless boot crashes right at Python init. The upstream-correct one-char fix
// is `stream.node?.node_ops?.getattr`. TODO(report to emscripten upstream).
//
// SCOPE: NODERAWFS / node ONLY. The browser build uses WASMFS, which has no
// NODEFS.fstat and no createStandardStreams — it never hits this path and is
// unaffected. This shim is added via --pre-js ONLY to the node `blender` target
// (blender_web_node_binary in patches/platform_wasm.cmake), and additionally
// self-gates on ENVIRONMENT_IS_NODE. Baked into blender.js so `node blender.js …`
// works with no external launcher.
//
// Runs as a preRun callback (main-thread, after FS/NODERAWFS staticInit assigns
// FS.fstat, before main). Under -sPROXY_TO_PTHREAD the fstat syscall is proxied to
// the main thread and executes main-thread FS.fstat, which is exactly what we patch.
Module.preRun = Module.preRun || [];
Module.preRun.push(function bw_patch_noderawfs_fstat() {
  if (typeof ENVIRONMENT_IS_NODE === "undefined" || !ENVIRONMENT_IS_NODE) {
    return;
  }
  if (typeof FS === "undefined" || !FS || typeof FS.fstat !== "function") {
    return;
  }
  var nodeFs = require("node:fs");
  // Reinstall fstat with the `stream.node` guard the emscripten version is missing.
  FS.fstat = function bw_fstat(fd) {
    var stream = FS.getStreamChecked(fd);
    var getattr =
      (stream.stream_ops && stream.stream_ops.getattr) ||
      (stream.node && stream.node.node_ops && stream.node.node_ops.getattr);
    if (getattr) {
      return getattr(stream.stream_ops && stream.stream_ops.getattr ? stream : stream.node);
    }
    // NODERAWFS raw-fd stream (e.g. the standard streams): stat the real node fd.
    return nodeFs.fstatSync(stream.nfd);
  };
});
