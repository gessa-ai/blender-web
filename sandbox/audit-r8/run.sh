#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later

set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
AUDIT_TMP="$(mktemp -d "${TMPDIR:-/tmp}/bw-audit-r8.XXXXXX")"
cleanup() {
  rm -rf -- "$AUDIT_TMP"
}
trap cleanup EXIT

CXX_BIN="${CXX:-clang++-17}"
EMXX_BIN="$ROOT/tools/emsdk/upstream/emscripten/em++"
NODE_BIN="$ROOT/tools/emsdk/node/22.16.0_64bit/bin/node"
PYTHON_BIN="${PYTHON:-$ROOT/.host-tools/bin/python3.13}"
CONTEXT_CC="$ROOT/platform_web/ghost/GHOST_ContextWGPUWeb.cc"
CONTEXT_HH="$ROOT/platform_web/ghost/GHOST_ContextWGPUWeb.hh"
CALLBACK_CENSUS="$HERE/callback_census.py"

# Source-compliance: the public header must describe the shipping inheritance and
# both initialization paths without reviving the retired standalone-class claim.
HEADER_DOC="$(sed -n '1,/^#pragma once$/p' "$CONTEXT_HH" |
  sed -E 's/^[[:space:]]*\*[[:space:]]?//' |
  tr '\n' ' ' |
  tr -s '[:space:]' ' ')"
if ! grep -Fq 'class GHOST_ContextWGPUWeb : public GHOST_Context {' "$CONTEXT_HH" ||
   ! grep -Fq 'The shipping class subclasses `GHOST_Context`.' <<<"$HEADER_DOC" ||
   ! grep -Fq '`initializeDrawingContext()` imports the device and, for a presentable window, the surface/backbuffer acquired asynchronously on the WM worker before `main()`.' <<<"$HEADER_DOC" ||
   ! grep -Fq '`initAsync()` remains the callback-driven acquisition path for standalone proofs.' <<<"$HEADER_DOC" ||
   ! grep -Fq 'shared `CallbackLifetime` execution gate; destruction closes admission and waits for admitted work before releasing context storage.' <<<"$HEADER_DOC" ||
   grep -Fiq 'one-time top-level await' <<<"$HEADER_DOC" ||
   grep -Eiq 'does[[:space:]]+not[[:space:]]+subclass|not[[:space:]]+a[[:space:]]+`?GHOST_Context`?[[:space:]]+subclass' <<<"$HEADER_DOC"; then
  echo "ERROR: GHOST_ContextWGPUWeb inheritance lifecycle documentation is stale" >&2
  exit 1
fi

# Bind the helper contract to every shipping completion that can outlive its
# non-reference-counted GHOST owner.  A passing standalone helper that the
# production context never calls is not evidence.
"$PYTHON_BIN" "$CALLBACK_CENSUS" "$CONTEXT_CC" --self-test \
  >"$AUDIT_TMP/callback-census.log"
grep -Fqx \
  "CALLBACK_CENSUS_PASS roles=8 owner_deliveries=7 fallback_loss=1" \
  "$AUDIT_TMP/callback-census.log"
grep -Fqx \
  "CALLBACK_CENSUS_SELFTEST_PASS controls=3 dead_text_alias=reject implicit_capture=reject extra_callback=reject legacy_false_positive=1" \
  "$AUDIT_TMP/callback-census.log"
grep -Fq 'std::shared_ptr<ghost_web::DeviceCallbackState> device_state_' "$CONTEXT_HH"
grep -Fq 'std::make_shared<ghost_web::DeviceCallbackState>(' "$CONTEXT_CC"
grep -Fq 'ghost_web_preinit_device_loss_generation(), imported_device_loss_observation' \
  "$CONTEXT_CC"
grep -Fq 'callback_lifetime_->invalidate();' "$CONTEXT_CC"
PROPAGATE_BODY="$(sed -n \
  '/void GHOST_ContextWGPUWeb::propagateDeviceLoss()/,/void GHOST_ContextWGPUWeb::finishSetup()/p' \
  "$CONTEXT_CC")"
if ! grep -Fq 'completeInitialization(false);' <<<"$PROPAGATE_BODY"; then
  echo "ERROR: terminal device loss does not settle pending initialization" >&2
  exit 1
fi
COMPLETE_BODY="$(sed -n \
  '/void GHOST_ContextWGPUWeb::completeInitialization(/,/bool GHOST_ContextWGPUWeb::deviceIsUsable()/p' \
  "$CONTEXT_CC")"
if ! grep -Fq 'ReadyCallback on_ready = std::move(on_ready_);' <<<"$COMPLETE_BODY" ||
   ! grep -Fq 'on_ready_ = nullptr;' <<<"$COMPLETE_BODY" ||
   grep -Fq 'on_ready_(success);' <<<"$COMPLETE_BODY"; then
  echo "ERROR: ready callback is not detached from owner storage before delivery" >&2
  exit 1
fi
if [[ "$(grep -Fc 'auto owner_execution = lifetime->enter();' "$CONTEXT_CC")" -ne 9 ||
      "$(grep -Fc 'auto owner_execution = lifetime->enter();' "$CONTEXT_HH")" -ne 8 ]]; then
  echo "ERROR: shipping public owner-execution census changed" >&2
  exit 1
fi

if [[ "$($NODE_BIN --version)" != "v22.16.0" ]]; then
  echo "ERROR: pinned Node 22.16.0 is unavailable" >&2
  exit 1
fi
if [[ "$($EMXX_BIN --version | sed -n '1s/.* \([0-9][0-9.]*\) (.*/\1/p')" != "6.0.5" ]]; then
  echo "ERROR: pinned em++ 6.0.5 is unavailable" >&2
  exit 1
fi

"$CXX_BIN" \
  -std=c++17 \
  -O1 \
  -g \
  -fno-omit-frame-pointer \
  -fsanitize=address \
  -pthread \
  -I"$ROOT/platform_web/ghost" \
  "$HERE/ghost_callback_gap_test.cc" \
  -o "$AUDIT_TMP/ghost_callback_gap_test_native"

"$EMXX_BIN" \
  -std=c++17 \
  -O1 \
  -pthread \
  -sPTHREAD_POOL_SIZE=2 \
  -sENVIRONMENT=node \
  -sEXIT_RUNTIME=1 \
  -sALLOW_MEMORY_GROWTH=1 \
  -I"$ROOT/platform_web/ghost" \
  "$HERE/ghost_callback_gap_test.cc" \
  -o "$AUDIT_TMP/ghost_callback_gap_test_wasm.js"

timeout 15s "$AUDIT_TMP/ghost_callback_gap_test_native" \
  >"$AUDIT_TMP/accepted-native.log" 2>&1
timeout 15s "$NODE_BIN" "$AUDIT_TMP/ghost_callback_gap_test_wasm.js" \
  >"$AUDIT_TMP/accepted-wasm.log" 2>&1
if ! cmp -s "$AUDIT_TMP/accepted-native.log" "$AUDIT_TMP/accepted-wasm.log"; then
  echo "ERROR: native and wasm32 callback contracts differ" >&2
  exit 1
fi
grep -Fqx \
  "CONTRACT ghost_owner_lifetime PASS concurrent=1 reentrant=1 delayed=blocked" \
  "$AUDIT_TMP/accepted-native.log"
grep -Fqx \
  "CONTRACT ghost_owner_serialization PASS concurrent=serialized nested=1" \
  "$AUDIT_TMP/accepted-native.log"
grep -Fqx \
  "CONTRACT ghost_owner_execution PASS callback_owner=serialized cleanup=quiescent" \
  "$AUDIT_TMP/accepted-native.log"
grep -Fqx \
  "CONTRACT ghost_destruction_admission PASS nested=blocked queued=blocked" \
  "$AUDIT_TMP/accepted-native.log"
grep -Fqx \
  "CONTRACT ghost_imported_loss_callback PASS pending=allow settled=block sticky=1 replaced=block" \
  "$AUDIT_TMP/accepted-native.log"
grep -Fqx \
  "CONTRACT ghost_loss_init_settlement PASS backbuffer=failed_once configuration=failed_once pending=cleared raw_owner=0" \
  "$AUDIT_TMP/accepted-native.log"
grep -Fqx \
  "CONTRACT ghost_ready_callback_lifetime PASS self_destroy=continued member_cleared=1" \
  "$AUDIT_TMP/accepted-native.log"
grep -Fqx \
  "CONTRACT ghost_shipping_callback_matrix PASS roles=8 active=7 loss=1 post_loss=blocked post_destroy=blocked" \
  "$AUDIT_TMP/accepted-native.log"

set +e
ASAN_OPTIONS="abort_on_error=1:detect_leaks=0:symbolize=0" \
  timeout 15s "$AUDIT_TMP/ghost_callback_gap_test_native" --unsafe-owner-race \
  >"$AUDIT_TMP/unsafe-owner-race.log" 2>&1
RACE_RC=$?
set -e
if [[ "$RACE_RC" -eq 0 || "$RACE_RC" -eq 124 ]]; then
  echo "ERROR: unsafe owner race did not reach the expected ASan rejection" >&2
  exit 1
fi
if ! grep -Fq "heap-use-after-free" "$AUDIT_TMP/unsafe-owner-race.log"; then
  echo "ERROR: unsafe owner race failed without the expected ASan diagnosis" >&2
  exit 1
fi

set +e
ASAN_OPTIONS="abort_on_error=1:detect_leaks=0:symbolize=0" \
  timeout 15s "$AUDIT_TMP/ghost_callback_gap_test_native" --unsafe-ready-self-destroy \
  >"$AUDIT_TMP/unsafe-ready-self-destroy.log" 2>&1
READY_RC=$?
set -e
if [[ "$READY_RC" -eq 0 || "$READY_RC" -eq 124 ]]; then
  echo "ERROR: unsafe ready self-destruction did not reach the expected ASan rejection" >&2
  exit 1
fi
if ! grep -Fq "heap-use-after-free" "$AUDIT_TMP/unsafe-ready-self-destroy.log"; then
  echo "ERROR: unsafe ready self-destruction failed without the expected ASan diagnosis" >&2
  exit 1
fi

echo "AUDIT_R8_GHOST_CALLBACK_PASS inheritance_doc=1 source_roles=8 source_controls=3 shipping_matrix=8 imported_loss=1 loss_init_settlement=2 ready_self_destroy=1 owner_concurrent=1 owner_serialized=1 owner_execution=1 cleanup_quiescent=1 destruction_admission=1 nested=1 owner_reentrant=1 unsafe_asan=2"
