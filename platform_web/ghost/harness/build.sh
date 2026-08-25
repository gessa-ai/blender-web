#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Build the standalone GHOST-web event harness: the platform_web/ghost classes +
# the REAL upstream GHOST base classes (read-only include) -> a wasm test module.
# Uses the shipping PROXY_TO_PTHREAD topology: OPFS mount and HTML5 window-state
# transitions are worker-owned, and the server must provide COOP/COEP.
#
# Usage: platform_web/ghost/harness/build.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
GHOST="$ROOT/upstream/intern/ghost"
WEB="$ROOT/platform_web/ghost"
OUT="$WEB/harness/build"
mkdir -p "$OUT"
cp "$ROOT/platform_web/shell/diagnostics-bootstrap.js" "$OUT/diagnostics-bootstrap.js"

# shellcheck disable=SC1091
source "$ROOT/tools/emsdk/emsdk_env.sh" >/dev/null 2>&1

# Web GHOST classes + harness.
SRC=(
  "$WEB/GHOST_SystemWeb.cc"
  "$WEB/GHOST_WindowWeb.cc"
  "$WEB/GHOST_EventBridgeWeb.cc"
  "$WEB/harness/test_ghost_web.cc"
)
# Minimal real GHOST base classes needed to link a concrete system+window
# (no X11/SDL/Cocoa, no GL/Vulkan). GHOST_Window installs a GHOST_ContextNone by
# default, so the base + None context are required; GHOST_ISystem.cc is intentionally
# NOT linked (we instantiate GHOST_SystemWeb directly, not via createSystem()).
SRC+=(
  "$GHOST/intern/GHOST_System.cc"
  "$GHOST/intern/GHOST_Window.cc"
  "$GHOST/intern/GHOST_EventManager.cc"
  "$GHOST/intern/GHOST_WindowManager.cc"
  "$GHOST/intern/GHOST_TimerManager.cc"
  "$GHOST/intern/GHOST_ModifierKeys.cc"
  "$GHOST/intern/GHOST_Buttons.cc"
  "$GHOST/intern/GHOST_Context.cc"
  "$GHOST/intern/GHOST_ContextNone.cc"
  "$GHOST/intern/GHOST_Rect.cc"
)
# guardedalloc: GHOST_Types.hh pulls MEM_guardedalloc.h (MEM_CXX_CLASS_ALLOC_FUNCS).
GA="$ROOT/upstream/intern/guardedalloc"
SRC+=(
  "$GA/intern/mallocn.cc"
  "$GA/intern/mallocn_lockfree_impl.cc"
  "$GA/intern/mallocn_guarded_impl.cc"
  "$GA/intern/memory_usage.cc"
  "$GA/intern/leak_detector.cc"
)

emcc \
  -pthread \
  -std=c++17 -O1 -g2 --profiling-funcs \
  -fexceptions -funsigned-char -DWITH_INPUT_IME \
  -I"$WEB" -I"$GHOST" -I"$GHOST/intern" \
  -I"$GA" -I"$ROOT/upstream/intern/atomic" \
  "${SRC[@]}" \
  -sMODULARIZE=1 -sEXPORT_NAME=createGhostTest \
  -sALLOW_MEMORY_GROWTH=1 -sEXIT_RUNTIME=0 -sWASMFS=1 -sFORCE_FILESYSTEM=1 \
  -sPROXY_TO_PTHREAD=1 -sPTHREAD_POOL_SIZE=2 \
  -sEXPORTED_RUNTIME_METHODS=callMain,printErr \
  -o "$OUT/ghost_web_test.js"

echo "built: $OUT/ghost_web_test.js ($(du -h "$OUT/ghost_web_test.wasm" | cut -f1) wasm)"
