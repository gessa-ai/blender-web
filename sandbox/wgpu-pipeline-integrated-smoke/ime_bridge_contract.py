#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later

"""Bind browser composition ownership, ordering, and GHOST IME enablement."""

from __future__ import annotations

import argparse
from pathlib import Path


def require_once(source: str, token: str, label: str) -> None:
    if source.count(token) != 1:
        raise ValueError(f"{label} requires exactly one {token!r}")


def require_order(source: str, tokens: tuple[str, ...], label: str) -> None:
    positions = [source.find(token) for token in tokens]
    if any(position < 0 for position in positions) or positions != sorted(positions):
        raise ValueError(f"{label} ordering differs: {tokens!r}")


def validate(files: dict[str, str]) -> None:
    bridge = files["bridge"]
    bridge_header = files["bridge_header"]
    system = files["system"]
    window = files["window"]
    window_header = files["window_header"]
    config = files["config"]
    root_cmake = files["root_cmake"]
    patch = files["patch"]
    series = files["series"]

    for token in (
        "constexpr uint64_t IME_QUEUE_CAPACITY = 64;",
        "std::array<std::atomic<ImeMessage *>, IME_QUEUE_CAPACITY> g_ime_slots{};",
        "std::atomic<bool> g_ime_enabled{false};",
        "g_ime_enabled.load(std::memory_order_acquire)",
        "class GHOST_EventIMEWeb : public GHOST_Event",
        'extern "C" EMSCRIPTEN_KEEPALIVE int bw_shell_ime_publish(',
        "std::string(text_length == 0 ? \"\" : text, size_t(text_length))",
        "slot.store(message, std::memory_order_release);",
        "slot.exchange(nullptr, std::memory_order_acq_rel)",
        "data.result = std::move(message->text);",
        "sys.pushEvent(std::make_unique<GHOST_EventIMEWeb>(",
    ):
        require_once(bridge, token, "worker ownership bridge")
    if bridge.count("data.composite = std::move(message->text);") != 2:
        raise ValueError("start/update do not both publish owned composition text")
    if bridge.count("g_ime_dropped.fetch_add(1, std::memory_order_relaxed);") != 3:
        raise ValueError("disabled/invalid, full, and allocation rejection paths are not diagnosed")
    require_order(
        bridge,
        (
            "slot.load(std::memory_order_acquire) != nullptr",
            "new ImeMessage",
            "slot.store(message, std::memory_order_release);",
        ),
        "producer publication",
    )
    require_order(
        bridge,
        (
            "slot.exchange(nullptr, std::memory_order_acq_rel)",
            "g_ime_read_sequence.store(sequence + 1",
            "sys.pushEvent(std::make_unique<GHOST_EventIMEWeb>(",
        ),
        "worker consumption",
    )

    require_once(bridge_header, "void set_ime_enabled(bool enabled);", "bridge header")
    require_once(bridge_header, "void poll_ime(GHOST_SystemWeb &sys);", "bridge header")
    require_once(window_header, "void beginIME(", "window header")
    require_once(window_header, "void endIME() override;", "window header")
    require_order(
        window,
        (
            "ghost_web_bridge::set_ime_enabled(true);",
            "MAIN_THREAD_EM_ASM_INT(",
            "if (!focused)",
        ),
        "IME begin",
    )
    window_end = window[window.index("void GHOST_WindowWeb::endIME()") :]
    require_order(
        window_end,
        (
            "void GHOST_WindowWeb::endIME()",
            "bridge.end();",
            "ghost_web_bridge::set_ime_enabled(false);",
        ),
        "IME end",
    )

    for token in (
        'input.addEventListener("compositionstart"',
        'input.addEventListener("compositionupdate"',
        'input.addEventListener("compositionend"',
        "publish(0, text, lengthBytesUTF8(text), -1, -1);",
        "publish(1, text, lengthBytesUTF8(text), -1, -1);",
        "publish(2, text, -1, -1, -1);",
        'publish(3, "", -1, -1, -1);',
        'Object.defineProperty(globalThis, "__bwImeBridge"',
    ):
        require_once(system, token, "browser composition bridge")
    if system.count("ghost_web_bridge::poll_ime(*this);") != 2:
        raise ValueError(
            "browser composition bridge requires main-loop and disposal drains"
        )
    capabilities = system[system.index("GHOST_TCapabilityFlag GHOST_SystemWeb::getCapabilities() const") :]
    capabilities = capabilities[: capabilities.index("char *GHOST_SystemWeb::getClipboard")]
    if "GHOST_kCapabilityInputIME" in capabilities:
        raise ValueError("implemented IME remains capability-masked")
    composition_end = system[system.index("publish(2, text, -1, -1, -1);") :]
    require_order(
        composition_end,
        (
            "publish(2, text, -1, -1, -1);",
            'publish(3, "", -1, -1, -1);',
            "composing = false;",
        ),
        "browser commit/end",
    )

    if not (
        "if(WITH_BLENDER_WEB_WINDOWED)\n  set(WITH_INPUT_IME        ON" in config
        and "else()\n  set(WITH_INPUT_IME        OFF" in config
        and "WIN32 OR APPLE OR WITH_GHOST_WEB OR" in root_cmake
    ):
        raise ValueError("IME is not scoped to the windowed web profile")
    require_once(patch, "+if(WIN32 OR APPLE OR WITH_GHOST_WEB OR", "numbered patch")
    require_once(series, "0280-ghost-web-input-ime-option.patch", "patch series")


def selfcheck(files: dict[str, str]) -> None:
    validate(files)
    mutations = (
        ("bridge", "IME_QUEUE_CAPACITY = 64", "IME_QUEUE_CAPACITY = 1"),
        ("bridge", "g_ime_enabled.load(std::memory_order_acquire)", "true"),
        ("bridge", "slot.load(std::memory_order_acquire) != nullptr", "false"),
        ("bridge", "slot.store(message, std::memory_order_release);", "slot.store(message);"),
        ("bridge", "slot.exchange(nullptr, std::memory_order_acq_rel)", "slot.load()"),
        ("bridge", "data.composite = std::move(message->text);", "data.result = message->text;"),
        ("bridge", "data.result = std::move(message->text);", "data.composite = message->text;"),
        ("bridge_header", "void poll_ime(GHOST_SystemWeb &sys);", ""),
        ("window", "ghost_web_bridge::set_ime_enabled(true);", ""),
        ("window", "bridge.end();", ""),
        ("window_header", "void endIME() override;", "void endIME();"),
        ("system", 'input.addEventListener("compositionstart"', 'input.addEventListener("input"'),
        ("system", "publish(1, text, lengthBytesUTF8(text), -1, -1);", ""),
        ("system", "publish(2, text, -1, -1, -1);", ""),
        ("system", 'publish(3, "", -1, -1, -1);', ""),
        ("system", "ghost_web_bridge::poll_ime(*this);", ""),
        ("system", "GHOST_kCapabilityWindowDecorationStyles |",
                   "GHOST_kCapabilityInputIME | GHOST_kCapabilityWindowDecorationStyles |"),
        ("config", "set(WITH_INPUT_IME        ON", "set(WITH_INPUT_IME        OFF"),
        ("root_cmake", " OR WITH_GHOST_WEB OR", " OR"),
        ("patch", "+if(WIN32 OR APPLE OR WITH_GHOST_WEB OR", "+if(WIN32 OR APPLE OR"),
        ("series", "0280-ghost-web-input-ime-option.patch", ""),
    )
    for index, (name, old, new) in enumerate(mutations, start=1):
        mutated = dict(files)
        if old not in mutated[name]:
            raise ValueError(f"mutation {index} input is absent: {name}/{old!r}")
        mutated[name] = mutated[name].replace(old, new, 1)
        try:
            validate(mutated)
        except ValueError:
            continue
        raise ValueError(f"mutation {index} was accepted")


def validate_runtime(runtime: str) -> None:
    for token in (
        "__bwImeBridge",
        "bw-ime-input",
        "compositionstart",
        "compositionupdate",
        "compositionend",
        "_bw_shell_ime_publish",
        "_bw_shell_ime_consumed_count",
    ):
        if token not in runtime:
            raise ValueError(f"baked runtime omits {token!r}")


def main() -> int:
    parser = argparse.ArgumentParser()
    for name in (
        "bridge", "bridge_header", "system", "window", "window_header",
        "config", "root_cmake", "patch", "series",
    ):
        parser.add_argument(name, type=Path)
    parser.add_argument("--runtime", type=Path)
    parser.add_argument("--selfcheck", action="store_true")
    args = parser.parse_args()
    files = {name: getattr(args, name).read_text(encoding="utf-8") for name in (
        "bridge", "bridge_header", "system", "window", "window_header",
        "config", "root_cmake", "patch", "series",
    )}
    selfcheck(files) if args.selfcheck else validate(files)
    if args.runtime:
        validate_runtime(args.runtime.read_text(encoding="utf-8"))
    print(
        "IME_BRIDGE_CONTRACT PASS queue=spsc64 ownership=utf8-heap "
        "events=start,update,commit,end focus=caret,canvas capability=on mutations=21 "
        f"runtime={'baked' if args.runtime else 'source'}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
