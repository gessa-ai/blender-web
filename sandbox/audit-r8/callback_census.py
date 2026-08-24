#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later

"""Structurally bind every spontaneous GHOST WebGPU callback registration.

This intentionally uses a small C++ lexer/balanced-delimiter parser rather than
raw source counts.  The gate inventories every literal AllowSpontaneous call by
its enclosing method, exact callee, mode/callback argument positions, and callback
shape, then binds every owner-affine completion to the shared lifetime gate.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
import sys


class ContractError(RuntimeError):
    pass


@dataclass(frozen=True)
class Token:
    text: str
    kind: str
    start: int
    end: int
    line: int


@dataclass(frozen=True)
class Call:
    callee: str
    leaf: str
    name_index: int
    open_index: int
    close_index: int
    arguments: tuple[tuple[int, int], ...]


@dataclass(frozen=True)
class Lambda:
    start_index: int
    capture_close_index: int
    parameter_range: tuple[int, int] | None
    body_open_index: int
    body_close_index: int


@dataclass(frozen=True)
class Role:
    name: str
    method: str
    callee: str
    argument: int
    captures: tuple[str, ...]
    delivery_gate: str | None
    checks_device_state: bool = False
    label: str | None = None


@dataclass(frozen=True)
class SpontaneousRegistration:
    name: str
    method: str
    callee: str
    mode_argument: int
    callback_argument: int
    count: int
    role: str | None = None
    callback_expression: str | None = None


ROLES = (
    Role(
        "adapter_acquisition",
        "requestAdapter",
        "RequestAdapter",
        2,
        ("callback_lifetime",),
        "callback_lifetime",
    ),
    Role(
        "fallback_device_loss",
        "requestDevice",
        "SetDeviceLostCallback",
        1,
        ("device_state", "device_loss_lifetime"),
        None,
    ),
    Role(
        "device_acquisition",
        "requestDevice",
        "RequestDevice",
        2,
        ("callback_lifetime",),
        "callback_lifetime",
    ),
    Role(
        "backbuffer_creation",
        "ensureBackbuffer",
        "scoped_handle_create",
        3,
        ("lifetime", "device_state", "candidate_width", "candidate_height"),
        "lifetime",
        True,
    ),
    Role(
        "surface_configuration",
        "ensureBackbuffer",
        "popErrorScopes",
        2,
        (
            "lifetime",
            "device_state",
            "candidate=std::move(candidate)",
            "candidate_width",
            "candidate_height",
        ),
        "lifetime",
        True,
        "surface configuration",
    ),
    Role(
        "present_pipeline_creation",
        "ensurePresentPipeline",
        "present_pipeline_create_scoped",
        6,
        ("lifetime", "device_state"),
        "lifetime",
        True,
    ),
    Role(
        "present_submission",
        "presentBackbuffer",
        "present_frame_encode_submit_scoped",
        9,
        ("lifetime", "device_state", "queue"),
        "lifetime",
        True,
    ),
    Role(
        "present_completion",
        "presentBackbuffer",
        "present_frame_encode_submit_scoped",
        11,
        (
            "lifetime",
            "device_state",
            "surface_width",
            "surface_height",
            "reconfigure_after_present",
        ),
        "lifetime",
        True,
    ),
)


SPONTANEOUS_MODE = "wgpu::CallbackMode::AllowSpontaneous"

SPONTANEOUS_REGISTRATIONS = (
    SpontaneousRegistration(
        "error_scope_settlement",
        "popErrorScopes",
        "device.PopErrorScope",
        0,
        1,
        3,
        callback_expression="settle",
    ),
    SpontaneousRegistration(
        "adapter_acquisition",
        "requestAdapter",
        "instance_.RequestAdapter",
        1,
        2,
        1,
        role="adapter_acquisition",
    ),
    SpontaneousRegistration(
        "fallback_device_loss",
        "requestDevice",
        "desc.SetDeviceLostCallback",
        0,
        1,
        1,
        role="fallback_device_loss",
    ),
    SpontaneousRegistration(
        "device_acquisition",
        "requestDevice",
        "adapter_.RequestDevice",
        1,
        2,
        1,
        role="device_acquisition",
    ),
)


MULTI_PUNCTUATION = (
    "<=>",
    "->*",
    "...",
    "::",
    "->",
    "&&",
    "||",
    "==",
    "!=",
    "<=",
    ">=",
    "++",
    "--",
    "<<",
    ">>",
    "+=",
    "-=",
    "*=",
    "/=",
    "%=",
    "&=",
    "|=",
    "^=",
    ".*",
)


def lex_cpp(source: str) -> list[Token]:
    tokens: list[Token] = []
    index = 0
    line = 1
    length = len(source)

    while index < length:
        char = source[index]
        if char.isspace():
            line += char == "\n"
            index += 1
            continue
        if source.startswith("//", index):
            end = source.find("\n", index + 2)
            if end == -1:
                break
            index = end
            continue
        if source.startswith("/*", index):
            end = source.find("*/", index + 2)
            if end == -1:
                raise ContractError(f"unterminated block comment at line {line}")
            line += source.count("\n", index, end + 2)
            index = end + 2
            continue
        if char in {'"', "'"}:
            start = index
            start_line = line
            quote = char
            index += 1
            while index < length:
                if source[index] == "\\":
                    index += 2
                    continue
                if source[index] == quote:
                    index += 1
                    break
                line += source[index] == "\n"
                index += 1
            else:
                raise ContractError(f"unterminated literal at line {start_line}")
            tokens.append(Token(source[start:index], "literal", start, index, start_line))
            continue
        if char.isalpha() or char == "_":
            start = index
            start_line = line
            index += 1
            while index < length and (source[index].isalnum() or source[index] == "_"):
                index += 1
            tokens.append(Token(source[start:index], "identifier", start, index, start_line))
            continue
        if char.isdigit():
            start = index
            start_line = line
            index += 1
            while index < length and (source[index].isalnum() or source[index] in "._'"):
                index += 1
            tokens.append(Token(source[start:index], "number", start, index, start_line))
            continue

        punctuation = next(
            (value for value in MULTI_PUNCTUATION if source.startswith(value, index)), char
        )
        tokens.append(Token(punctuation, "punctuation", index, index + len(punctuation), line))
        index += len(punctuation)

    return tokens


class SourceModel:
    def __init__(self, source: str):
        self.source = source
        self.tokens = lex_cpp(source)
        self.pairs = self._build_pairs()
        self._lambda_cache: dict[int, Lambda | None] = {}

    def _build_pairs(self) -> dict[int, int]:
        opening = {"(": ")", "[": "]", "{": "}"}
        closing = {value: key for key, value in opening.items()}
        stack: list[tuple[str, int]] = []
        pairs: dict[int, int] = {}
        for index, token in enumerate(self.tokens):
            if token.text in opening:
                stack.append((token.text, index))
            elif token.text in closing:
                if not stack or stack[-1][0] != closing[token.text]:
                    raise ContractError(
                        f"unbalanced {token.text!r} at source line {token.line}"
                    )
                _, open_index = stack.pop()
                pairs[open_index] = index
                pairs[index] = open_index
        if stack:
            token = self.tokens[stack[-1][1]]
            raise ContractError(f"unclosed {token.text!r} at source line {token.line}")
        return pairs

    def normalized(self, token_range: tuple[int, int]) -> str:
        start, end = token_range
        return "".join(token.text for token in self.tokens[start:end])

    def split_top_level(self, start: int, end: int) -> tuple[tuple[int, int], ...]:
        if start >= end:
            return ()
        result: list[tuple[int, int]] = []
        item_start = start
        index = start
        while index < end:
            token = self.tokens[index]
            if token.text in {"(", "[", "{"}:
                close = self.pairs[index]
                if close >= end:
                    raise ContractError(
                        f"delimiter crosses structural boundary at line {token.line}"
                    )
                index = close + 1
                continue
            if token.text == ",":
                result.append((item_start, index))
                item_start = index + 1
            index += 1
        result.append((item_start, end))
        return tuple(result)

    def call_at(self, name_index: int) -> Call | None:
        if (
            name_index < 0
            or name_index + 1 >= len(self.tokens)
            or self.tokens[name_index].kind != "identifier"
            or self.tokens[name_index + 1].text != "("
        ):
            return None
        open_index = name_index + 1
        close_index = self.pairs[open_index]
        callee_start = name_index
        while (
            callee_start >= 2
            and self.tokens[callee_start - 1].text in {".", "->", "::"}
            and self.tokens[callee_start - 2].kind == "identifier"
        ):
            callee_start -= 2
        return Call(
            self.normalized((callee_start, name_index + 1)),
            self.tokens[name_index].text,
            name_index,
            open_index,
            close_index,
            self.split_top_level(open_index + 1, close_index),
        )

    def calls(self, token_range: tuple[int, int], leaf: str | None = None) -> list[Call]:
        start, end = token_range
        result: list[Call] = []
        for index in range(start, end - 1):
            if leaf is not None and self.tokens[index].text != leaf:
                continue
            call = self.call_at(index)
            if call is not None and call.close_index < end:
                result.append(call)
        return result

    def lambda_at(self, start_index: int) -> Lambda | None:
        if start_index in self._lambda_cache:
            return self._lambda_cache[start_index]
        if (
            start_index < 0
            or start_index >= len(self.tokens)
            or self.tokens[start_index].text != "["
        ):
            return None
        capture_close = self.pairs[start_index]
        index = capture_close + 1
        parameter_range: tuple[int, int] | None = None
        if index < len(self.tokens) and self.tokens[index].text == "(":
            parameter_close = self.pairs[index]
            parameter_range = (index + 1, parameter_close)
            index = parameter_close + 1
        while index < len(self.tokens) and self.tokens[index].text != "{":
            if self.tokens[index].text in {";", ",", ")", "]"}:
                self._lambda_cache[start_index] = None
                return None
            index += 1
        if index >= len(self.tokens) or self.tokens[index].text != "{":
            self._lambda_cache[start_index] = None
            return None
        result = Lambda(
            start_index,
            capture_close,
            parameter_range,
            index,
            self.pairs[index],
        )
        self._lambda_cache[start_index] = result
        return result

    def lambda_argument(self, call: Call, argument: int) -> Lambda:
        if argument >= len(call.arguments):
            raise ContractError(
                f"{call.callee} has {len(call.arguments)} arguments, expected index {argument}"
            )
        start, end = call.arguments[argument]
        callback = self.lambda_at(start)
        if callback is None or callback.body_close_index + 1 != end:
            line = self.tokens[call.name_index].line
            raise ContractError(
                f"{call.callee} argument {argument} is not one direct lambda at line {line}"
            )
        return callback

    def captures(self, callback: Lambda) -> tuple[str, ...]:
        return tuple(
            self.normalized(item)
            for item in self.split_top_level(
                callback.start_index + 1, callback.capture_close_index
            )
        )

    def method_body(self, method: str) -> tuple[int, int]:
        candidates: list[tuple[int, int]] = []
        for index in range(len(self.tokens) - 4):
            if (
                self.tokens[index].text == "GHOST_ContextWGPUWeb"
                and self.tokens[index + 1].text == "::"
                and self.tokens[index + 2].text == method
                and self.tokens[index + 3].text == "("
            ):
                parameter_close = self.pairs[index + 3]
                body_index = parameter_close + 1
                while body_index < len(self.tokens) and self.tokens[body_index].text not in {
                    "{",
                    ";",
                }:
                    body_index += 1
                if body_index < len(self.tokens) and self.tokens[body_index].text == "{":
                    candidates.append((body_index + 1, self.pairs[body_index]))
        if len(candidates) != 1:
            raise ContractError(
                f"method {method} has {len(candidates)} structural definitions, expected 1"
            )
        return candidates[0]

    def direct_calls(self, callback: Lambda) -> list[Call]:
        result: list[Call] = []
        index = callback.body_open_index + 1
        while index < callback.body_close_index:
            nested = self.lambda_at(index) if self.tokens[index].text == "[" else None
            if nested is not None and nested.body_close_index < callback.body_close_index:
                index = nested.body_close_index + 1
                continue
            call = self.call_at(index)
            if call is not None and call.close_index < callback.body_close_index:
                result.append(call)
            index += 1
        return result

    def lambdas(self) -> list[Lambda]:
        result: list[Lambda] = []
        for index, token in enumerate(self.tokens):
            if token.text != "[":
                continue
            callback = self.lambda_at(index)
            if callback is not None:
                result.append(callback)
        return result

    def local_lambda(self, method: str, name: str) -> Lambda:
        start, end = self.method_body(method)
        candidates: list[Lambda] = []
        for index in range(start, end - 2):
            if self.tokens[index].text != name or self.tokens[index + 1].text != "=":
                continue
            callback = self.lambda_at(index + 2)
            if callback is not None and callback.body_close_index < end:
                candidates.append(callback)
        if len(candidates) != 1:
            raise ContractError(
                f"method {method}: found {len(candidates)} local lambdas named {name}, expected 1"
            )
        return candidates[0]


def one_call(model: SourceModel, role: Role) -> Call:
    method_body = model.method_body(role.method)
    candidates = model.calls(method_body, role.callee)
    if role.label is not None:
        candidates = [
            call
            for call in candidates
            if len(call.arguments) > 1
            and any(
                token.kind == "literal" and token.text == f'"{role.label}"'
                for token in model.tokens[call.arguments[1][0] : call.arguments[1][1]]
            )
        ]
    if len(candidates) != 1:
        suffix = f" labelled {role.label!r}" if role.label is not None else ""
        raise ContractError(
            f"role {role.name}: found {len(candidates)} {role.callee} calls{suffix}, expected 1"
        )
    return candidates[0]


def spontaneous_calls(model: SourceModel) -> dict[tuple[int, int], Call]:
    mode_token_count = sum(
        model.normalized((index, index + 5)) == SPONTANEOUS_MODE
        for index in range(len(model.tokens) - 4)
    )
    registrations: dict[tuple[int, int], Call] = {}
    for call in model.calls((0, len(model.tokens))):
        for argument, token_range in enumerate(call.arguments):
            if model.normalized(token_range) == SPONTANEOUS_MODE:
                registrations[(call.name_index, argument)] = call

    if len(registrations) != mode_token_count:
        raise ContractError(
            "every AllowSpontaneous token must be one complete call argument "
            f"(tokens={mode_token_count} registrations={len(registrations)})"
        )
    return registrations


def check_spontaneous_registration_census(
    model: SourceModel,
    role_calls: dict[str, Call],
    role_callbacks: dict[str, Lambda],
) -> int:
    registrations = spontaneous_calls(model)
    matched: set[tuple[int, int]] = set()

    for expected in SPONTANEOUS_REGISTRATIONS:
        method_start, method_end = model.method_body(expected.method)
        candidates = [
            (key, call)
            for key, call in registrations.items()
            if method_start <= call.name_index < method_end
            and call.callee == expected.callee
            and key[1] == expected.mode_argument
        ]
        if len(candidates) != expected.count:
            raise ContractError(
                f"spontaneous registration {expected.name}: found {len(candidates)} "
                f"{expected.callee} calls, expected {expected.count}"
            )

        for key, call in candidates:
            if expected.callback_argument >= len(call.arguments):
                raise ContractError(
                    f"spontaneous registration {expected.name}: callback argument is absent"
                )
            if expected.callback_expression is not None:
                actual = model.normalized(call.arguments[expected.callback_argument])
                if actual != expected.callback_expression:
                    raise ContractError(
                        f"spontaneous registration {expected.name}: callback is {actual!r}, "
                        f"expected {expected.callback_expression!r}"
                    )
            else:
                if expected.role is None:
                    raise ContractError(
                        f"spontaneous registration {expected.name}: owner role is unspecified"
                    )
                role_call = role_calls[expected.role]
                callback = model.lambda_argument(call, expected.callback_argument)
                if call.name_index != role_call.name_index or callback != role_callbacks[expected.role]:
                    raise ContractError(
                        f"spontaneous registration {expected.name}: owner callback is not the "
                        "lifetime-gated role callback"
                    )
            matched.add(key)

    if matched != set(registrations):
        unexpected = set(registrations) - matched
        missing = matched - set(registrations)
        raise ContractError(
            "shipping AllowSpontaneous registration census differs from the manifest "
            f"(unexpected={len(unexpected)} missing={len(missing)})"
        )

    settle = model.local_lambda("popErrorScopes", "settle")
    if model.captures(settle) != ("result",):
        raise ContractError("error-scope dispatcher must retain only its shared result")
    completions = [
        call for call in model.direct_calls(settle) if call.callee == "result->complete"
    ]
    if len(completions) != 1:
        raise ContractError(
            "error-scope dispatcher must invoke its owner-affine continuation exactly once"
        )

    return len(registrations)


def require_owner_parameter(model: SourceModel, role: Role, callback: Lambda) -> None:
    if callback.parameter_range is None:
        raise ContractError(f"role {role.name}: owner callback has no parameter")
    parameters = model.normalized(callback.parameter_range)
    if parameters not in {"GHOST_ContextWGPUWeb&owner", "GHOST_ContextWGPUWeb&"}:
        raise ContractError(
            f"role {role.name}: owner callback parameter is {parameters!r}"
        )


def check_delivery_role(
    model: SourceModel, role: Role, outer: Lambda
) -> tuple[int, int]:
    direct_deliveries = [call for call in model.direct_calls(outer) if call.leaf == "deliver"]
    if len(direct_deliveries) != 1:
        raise ContractError(
            f"role {role.name}: found {len(direct_deliveries)} direct owner deliveries, expected 1"
        )
    delivery = direct_deliveries[0]
    expected_callee = f"{role.delivery_gate}->deliver"
    if delivery.callee != expected_callee:
        raise ContractError(
            f"role {role.name}: delivery uses {delivery.callee!r}, expected {expected_callee!r}"
        )
    owner_callback = model.lambda_argument(delivery, 0)
    if model.captures(owner_callback) != ("&",):
        raise ContractError(
            f"role {role.name}: immediate owner callback must use the local [&] capture"
        )
    require_owner_parameter(model, role, owner_callback)
    if role.checks_device_state:
        state_checks = [
            call
            for call in model.direct_calls(owner_callback)
            if call.leaf == "device_state_allows_callback_work"
            and len(call.arguments) == 1
            and model.normalized(call.arguments[0]) == "device_state"
        ]
        if len(state_checks) != 1:
            raise ContractError(
                f"role {role.name}: expected one callback-time device-state check"
            )
    return delivery.name_index, owner_callback.start_index


def check_loss_role(model: SourceModel, role: Role, outer: Lambda) -> int:
    notifications = [
        call
        for call in model.direct_calls(outer)
        if call.callee == "ghost_web::fallback_device_loss_notify"
    ]
    if len(notifications) != 1:
        raise ContractError(
            f"role {role.name}: found {len(notifications)} fallback loss notifications, expected 1"
        )
    notification = notifications[0]
    if len(notification.arguments) != 3:
        raise ContractError(f"role {role.name}: fallback loss notification arity changed")
    if model.normalized(notification.arguments[0]) != "device_state" or model.normalized(
        notification.arguments[1]
    ) != "device_loss_lifetime":
        raise ContractError(f"role {role.name}: fallback loss state/gate arguments changed")
    owner_callback = model.lambda_argument(notification, 2)
    if model.captures(owner_callback):
        raise ContractError(f"role {role.name}: fallback owner callback must capture nothing")
    require_owner_parameter(model, role, owner_callback)
    propagation = [
        call
        for call in model.direct_calls(owner_callback)
        if call.callee == "owner.propagateDeviceLoss"
    ]
    if len(propagation) != 1:
        raise ContractError(f"role {role.name}: terminal owner propagation changed")
    return notification.name_index


def analyze(source: str) -> dict[str, int]:
    model = SourceModel(source)
    outer_starts: set[int] = set()
    role_calls: dict[str, Call] = {}
    role_callbacks: dict[str, Lambda] = {}
    delivery_names: set[int] = set()
    owner_callback_starts: set[int] = set()
    loss_notifications: set[int] = set()

    for role in ROLES:
        call = one_call(model, role)
        outer = model.lambda_argument(call, role.argument)
        captures = model.captures(outer)
        if captures != role.captures:
            raise ContractError(
                f"role {role.name}: captures {captures!r}, expected {role.captures!r}"
            )
        if any(model.tokens[index].text == "this" for index in range(outer.start_index, outer.body_close_index + 1)):
            raise ContractError(f"role {role.name}: asynchronous callback retains raw this")
        role_calls[role.name] = call
        role_callbacks[role.name] = outer
        outer_starts.add(outer.start_index)
        if role.delivery_gate is None:
            loss_notifications.add(check_loss_role(model, role, outer))
        else:
            delivery_name, owner_callback_start = check_delivery_role(model, role, outer)
            delivery_names.add(delivery_name)
            owner_callback_starts.add(owner_callback_start)

    spontaneous_registration_count = check_spontaneous_registration_census(
        model, role_calls, role_callbacks
    )

    every_delivery = {
        call.name_index
        for call in model.calls((0, len(model.tokens)), "deliver")
        if call.callee.endswith("->deliver")
    }
    if every_delivery != delivery_names:
        unexpected = every_delivery - delivery_names
        missing = delivery_names - every_delivery
        raise ContractError(
            "shipping owner-delivery census differs from the eight-role manifest "
            f"(unexpected={len(unexpected)} missing={len(missing)})"
        )

    every_loss_notification = {
        call.name_index
        for call in model.calls((0, len(model.tokens)), "fallback_device_loss_notify")
        if call.callee == "ghost_web::fallback_device_loss_notify"
    }
    if every_loss_notification != loss_notifications:
        raise ContractError("shipping fallback-loss callback census changed")

    guarded_names = {
        "callback_lifetime",
        "device_loss_lifetime",
        "device_state",
        "lifetime",
    }
    for callback in model.lambdas():
        captures = model.captures(callback)
        if any("this" in capture for capture in captures):
            raise ContractError(
                f"raw owner capture in lambda at line {model.tokens[callback.start_index].line}"
            )
        if any(capture in {"&", "="} for capture in captures) and callback.start_index not in owner_callback_starts:
            raise ContractError(
                "implicit capture is permitted only for the immediate owner lambda "
                f"at line {model.tokens[callback.start_index].line}"
            )
        captured_identifiers = {
            token.text
            for token in model.tokens[callback.start_index + 1 : callback.capture_close_index]
            if token.kind == "identifier"
        }
        if captured_identifiers & guarded_names and callback.start_index not in outer_starts:
            raise ContractError(
                "owner gate/state captured outside the explicit callback manifest "
                f"at line {model.tokens[callback.start_index].line}"
            )

    return {
        "roles": len(ROLES),
        "owner_deliveries": len(delivery_names),
        "fallback_loss": len(loss_notifications),
        "spontaneous_registrations": spontaneous_registration_count,
    }


def expect_rejected(name: str, source: str) -> None:
    try:
        analyze(source)
    except ContractError:
        return
    raise ContractError(f"mutation control {name!r} was incorrectly accepted")


def replace_first(source: str, old: str, new: str, name: str) -> str:
    if old not in source:
        raise ContractError(
            f"self-test {name}: expected at least one occurrence of {old!r}"
        )
    return source.replace(old, new, 1)


def run_self_test(source: str) -> None:
    # This is a deliberate false positive for the retired grep gate: replacing one real
    # delivery with an alias and compensating with dead comment text preserves its count of 7.
    dead_text_alias = replace_first(
        source,
        "callback_lifetime->deliver",
        "callback_gate->deliver",
        "dead-text alias",
    )
    dead_text_alias += "\n/* lifetime->deliver -- dead mutation-control text */\n"
    if dead_text_alias.count("lifetime->deliver") != 7:
        raise ContractError("self-test no longer reproduces the retired raw-count false positive")
    expect_rejected("dead-text alias", dead_text_alias)

    implicit_capture = replace_first(
        source, "[callback_lifetime](", "[&](", "implicit capture"
    )
    expect_rejected("implicit capture", implicit_capture)

    model = SourceModel(source)
    adapter_call = one_call(model, ROLES[0])
    call_start = model.tokens[adapter_call.name_index - 2].start
    call_end = model.tokens[adapter_call.close_index].end
    while call_end < len(source) and source[call_end].isspace():
        call_end += 1
    if call_end >= len(source) or source[call_end] != ";":
        raise ContractError("self-test could not locate the adapter-call terminator")
    call_end += 1

    raw_owner_alias = (
        source[:call_start]
        + "auto *owner_alias = this;\n"
        + "  device_.PopErrorScope(\n"
        + "      wgpu::CallbackMode::AllowSpontaneous,\n"
        + "      [owner_alias](wgpu::PopErrorScopeStatus, wgpu::ErrorType, wgpu::StringView) {\n"
        + "        owner_alias->requestAdapter();\n"
        + "      });\n  "
        + source[call_start:]
    )
    expect_rejected("raw owner alias", raw_owner_alias)

    duplicate_callback = source[:call_end] + "\n  " + source[call_start:call_end] + source[call_end:]
    expect_rejected("extra callback", duplicate_callback)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    try:
        source = args.source.read_text(encoding="utf-8")
        report = analyze(source)
        if args.self_test:
            run_self_test(source)
    except (ContractError, OSError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1

    print(
        "CALLBACK_CENSUS_PASS "
        f"roles={report['roles']} owner_deliveries={report['owner_deliveries']} "
        f"fallback_loss={report['fallback_loss']} "
        f"spontaneous_registrations={report['spontaneous_registrations']}"
    )
    if args.self_test:
        print(
            "CALLBACK_CENSUS_SELFTEST_PASS controls=4 "
            "dead_text_alias=reject implicit_capture=reject raw_owner_alias=reject "
            "extra_callback=reject legacy_false_positive=1"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
