#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later

"""Fail-closed contract for bounded GHOST-web callback-registration metadata."""

from __future__ import annotations

import argparse
from pathlib import Path


ACQUIRE_MARKER = "void *callback_registration_token_acquire()"
CALLBACK_MARKER = "GHOST_SystemWeb *callback_system(void *user_data)"
REGISTER_MARKER = "bool GHOST_SystemWeb::registerCanvasCallbacks()"
UNREGISTER_MARKER = "void GHOST_SystemWeb::unregisterCanvasCallbacks()"


def method(source: str, marker: str) -> str:
    start = source.find(marker)
    if start < 0:
        raise ValueError(f"missing method: {marker}")
    opening = source.find("{", start)
    if opening < 0:
        raise ValueError(f"missing method body: {marker}")
    depth = 0
    for offset in range(opening, len(source)):
        if source[offset] == "{":
            depth += 1
        elif source[offset] == "}":
            depth -= 1
            if depth == 0:
                return source[start : offset + 1]
    raise ValueError(f"unterminated method: {marker}")


def require_once(body: str, token: str, label: str) -> None:
    if body.count(token) != 1:
        raise ValueError(f"{label} requires exactly one {token!r}")


def replace_once(text: str, old: str, new: str) -> str:
    if text.count(old) != 1:
        raise ValueError(f"mutation input count differs for {old!r}")
    return text.replace(old, new, 1)


def validate(source: str, live_test: str) -> None:
    for token in (
        "constexpr uint32_t kCallbackRegistrationBudget = 4096;",
        "std::array<uint8_t, kCallbackRegistrationBudget> g_callback_registration_tokens{};",
        "std::atomic<uint32_t> g_callback_registration_token_count{0};",
        "std::atomic<void *> g_callback_registration{nullptr};",
        "std::atomic<GHOST_SystemWeb *> g_callback_system{nullptr};",
    ):
        require_once(source, token, "fixed token registry")
    for forbidden in (
        "struct CallbackRegistration",
        "g_callback_registrations",
        "std::vector<std::unique_ptr<CallbackRegistration>>",
    ):
        if forbidden in source:
            raise ValueError(f"registration metadata remains dynamically retained: {forbidden}")

    acquire = method(source, ACQUIRE_MARKER)
    for token in (
        "g_callback_registration_token_count.load(std::memory_order_relaxed)",
        "index < kCallbackRegistrationBudget",
        "g_callback_registration_token_count.compare_exchange_weak(",
        "return &g_callback_registration_tokens[index];",
        "return nullptr;",
    ):
        require_once(acquire, token, "token acquisition")
    if acquire.index("index < kCallbackRegistrationBudget") > acquire.index(
            "g_callback_registration_token_count.compare_exchange_weak("):
        raise ValueError("token acquisition mutates the count before checking the budget")

    callback = method(source, CALLBACK_MARKER)
    for token in (
        "user_data == nullptr",
        "g_callback_registration.load(std::memory_order_acquire) != user_data",
        "g_callback_system.load(std::memory_order_acquire)",
    ):
        require_once(callback, token, "callback admission")
    if callback.index("g_callback_registration.load(") > callback.index(
            "g_callback_system.load("):
        raise ValueError("callback dereferences the owner before validating its opaque token")

    for token in (
        'extern "C" EMSCRIPTEN_KEEPALIVE double bw_callback_registration_attempt_count()',
        'extern "C" EMSCRIPTEN_KEEPALIVE double bw_callback_registration_budget()',
        'extern "C" EMSCRIPTEN_KEEPALIVE double bw_callback_registration_metadata_bytes()',
        "return double(g_callback_registration_token_count.load(std::memory_order_relaxed));",
        "return double(kCallbackRegistrationBudget);",
        "return double(sizeof(g_callback_registration_tokens));",
    ):
        require_once(source, token, "bounded-metadata diagnostics")

    registration = method(source, REGISTER_MARKER)
    for token in (
        "void *user_data = callback_registration_token_acquire();",
        "if (user_data == nullptr)",
        "callback registration token budget exhausted",
        "callback_user_data_ = user_data;",
        "g_callback_system.store(this, std::memory_order_release);",
        "g_callback_registration.store(user_data, std::memory_order_release);",
        "callbacks_registered_ = true;",
    ):
        require_once(registration, token, "registration publication")
    acquired = registration.index("callback_registration_token_acquire()")
    transaction = registration.index(
        "ghost_web::sequential_registration_transaction<kWebCallbackCount>(")
    owner = registration.index("g_callback_system.store(")
    token = registration.index("g_callback_registration.store(")
    published = registration.index("callbacks_registered_ = true;")
    if not acquired < transaction < owner < token < published:
        raise ValueError("callback owner/token publication is not transactional")

    unregistration = method(source, UNREGISTER_MARKER)
    for token in (
        "void *expected_registration = callback_user_data_;",
        "g_callback_registration.compare_exchange_strong(",
        "GHOST_SystemWeb *expected_system = this;",
        "g_callback_system.compare_exchange_strong(",
        "remove_html5_callback_prefix(canvas, win, callback_user_data_, kWebCallbackCount)",
        "callback_user_data_ = nullptr;",
    ):
        require_once(unregistration, token, "registration retirement")
    retire_token = unregistration.index("g_callback_registration.compare_exchange_strong(")
    retire_owner = unregistration.index("g_callback_system.compare_exchange_strong(")
    remove = unregistration.index("remove_html5_callback_prefix(")
    if not retire_token < retire_owner < remove:
        raise ValueError("callback token/owner retirement must precede listener removal")

    for token in (
        "const FAILED_REGISTRATION_SOAK = 128;",
        "const REPLACEMENT_REGISTRATION_SOAK = 256;",
        "input.id = \"bw-ime-input-missing\";",
        "failedResult !== 0",
        "expectedAttempts = beforeBudget.attempts + FAILED_REGISTRATION_SOAK + 1 +",
        "    REPLACEMENT_REGISTRATION_SOAK;",
        "afterBudget.attempts !== expectedAttempts",
        "afterBudget.budget !== 4096 || afterBudget.metadataBytes !== 4096",
        "afterListeners.active !== beforeListeners.active",
        "added !== removed",
        "const soakStaleSnapshot = await page.evaluate(() => {",
        "soakStaleSnapshot.captured !== 3",
        "registration-soak=failed:128,replacements:256",
    ):
        require_once(live_test, token, "real-worker soak")


def selfcheck(source: str, live_test: str) -> None:
    validate(source, live_test)
    mutations = (
        (replace_once(source, "kCallbackRegistrationBudget = 4096", "kCallbackRegistrationBudget = 4095"), live_test),
        (replace_once(source, "index < kCallbackRegistrationBudget", "index <= kCallbackRegistrationBudget"), live_test),
        (replace_once(source, "return &g_callback_registration_tokens[index];", "return nullptr;"), live_test),
        (replace_once(source, "g_callback_registration.load(std::memory_order_acquire) != user_data", "g_callback_registration.load(std::memory_order_acquire) == user_data"), live_test),
        (replace_once(source, "g_callback_system.load(std::memory_order_acquire)", "nullptr"), live_test),
        (replace_once(source, "void *user_data = callback_registration_token_acquire();", "void *user_data = this;"), live_test),
        (replace_once(source, "if (user_data == nullptr)", "if (false)"), live_test),
        (replace_once(source, "g_callback_system.store(this, std::memory_order_release);", ""), live_test),
        (replace_once(source, "g_callback_registration.store(user_data, std::memory_order_release);", ""), live_test),
        (replace_once(source, "g_callback_registration.compare_exchange_strong(", "g_callback_registration.store("), live_test),
        (replace_once(source, "return double(sizeof(g_callback_registration_tokens));", "return 0.0;"), live_test),
        (source, replace_once(live_test, "const FAILED_REGISTRATION_SOAK = 128;", "const FAILED_REGISTRATION_SOAK = 1;")),
        (source, replace_once(live_test, "const REPLACEMENT_REGISTRATION_SOAK = 256;", "const REPLACEMENT_REGISTRATION_SOAK = 1;")),
        (source, replace_once(live_test, "failedResult !== 0", "failedResult < 0")),
        (source, replace_once(live_test, "afterBudget.attempts !== expectedAttempts", "afterBudget.attempts < expectedAttempts")),
        (source, replace_once(live_test, "afterListeners.active !== beforeListeners.active", "afterListeners.active < beforeListeners.active")),
        (source, replace_once(live_test, "added !== removed", "added < removed")),
    )
    for index, (mutated_source, mutated_live) in enumerate(mutations, start=1):
        try:
            validate(mutated_source, mutated_live)
        except ValueError:
            continue
        raise ValueError(f"mutation {index} escaped the callback-registration soak contract")
    print(
        "CALLBACK_REGISTRATION_SOAK_CONTRACT PASS "
        f"mutations={len(mutations)} budget=4096 metadata=4096B failed=128 replacements=256"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("live_test", type=Path)
    parser.add_argument("--selfcheck", action="store_true")
    args = parser.parse_args()
    source = args.source.read_text(encoding="utf-8")
    live_test = args.live_test.read_text(encoding="utf-8")
    if args.selfcheck:
        selfcheck(source, live_test)
    else:
        validate(source, live_test)
        print("CALLBACK_REGISTRATION_SOAK_CONTRACT PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
