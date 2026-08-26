/* SPDX-FileCopyrightText: 2011-2023 Blender Authors
 * SPDX-FileCopyrightText: 2026 blender-web contributors
 *
 * SPDX-License-Identifier: GPL-2.0-or-later
 *
 * Ported for the web from intern/ghost/intern/GHOST_SystemX11.cc (convertXKey /
 * the GHOST_TKey mapping tables) @ fbe6228777e7. */

/** \file
 * \ingroup GHOST-web
 *
 * HTML5 `KeyboardEvent.code` -> #GHOST_TKey mapping for the web platform.
 *
 * We key off `KeyboardEvent.code` (the physical key position, e.g. "KeyA",
 * "Digit1", "ArrowLeft", "ShiftLeft", "Numpad0"), NOT `KeyboardEvent.key`.
 * `code` is layout-independent — the browser's closest equivalent to a hardware
 * scan-code — which matches GHOST's key-code contract (a physical key identity,
 * with the produced character carried separately in `utf8_buf`). This mirrors how
 * the native back-ends map hardware key-codes rather than the localized symbol.
 *
 * The produced Unicode text is taken from `KeyboardEvent.key` when it is a single
 * printable grapheme (see ghost_web_utf8_from_key); dead-keys / IME composition are
 * a documented deferral (notes/ghost-web-design.md), matching GOAL.md's SDL IME-gap
 * rationale.
 */

#pragma once

#include <cstdlib>
#include <cstring>

#include "GHOST_Types.hh"

/**
 * Map an HTML5 `KeyboardEvent.code` string to a #GHOST_TKey.
 * Returns #GHOST_kKeyUnknown for codes we do not (yet) map.
 */
static inline GHOST_TKey ghost_web_key_from_code(const char *code)
{
  if (code == nullptr || code[0] == '\0') {
    return GHOST_kKeyUnknown;
  }

  /* Programmatic ranges first (compact + exhaustive). */

  /* "KeyA" .. "KeyZ" -> GHOST_kKeyA .. GHOST_kKeyZ. */
  if (std::strncmp(code, "Key", 3) == 0 && code[3] >= 'A' && code[3] <= 'Z' && code[4] == '\0') {
    return GHOST_TKey(int(GHOST_kKeyA) + (code[3] - 'A'));
  }
  /* "Digit0" .. "Digit9" -> GHOST_kKey0 .. GHOST_kKey9. */
  if (std::strncmp(code, "Digit", 5) == 0 && code[5] >= '0' && code[5] <= '9' && code[6] == '\0') {
    return GHOST_TKey(int(GHOST_kKey0) + (code[5] - '0'));
  }
  /* "Numpad0" .. "Numpad9" -> GHOST_kKeyNumpad0 .. 9. */
  if (std::strncmp(code, "Numpad", 6) == 0 && code[6] >= '0' && code[6] <= '9' && code[7] == '\0') {
    return GHOST_TKey(int(GHOST_kKeyNumpad0) + (code[6] - '0'));
  }
  /* "F1" .. "F24" -> GHOST_kKeyF1 .. F24. */
  if (code[0] == 'F' && code[1] >= '1' && code[1] <= '9') {
    const int n = std::atoi(code + 1);
    if (n >= 1 && n <= 24) {
      return GHOST_TKey(int(GHOST_kKeyF1) + (n - 1));
    }
  }

  /* Named keys. Table kept in one place; linear scan is trivial for key events. */
  struct Entry {
    const char *code;
    GHOST_TKey key;
  };
  static const Entry table[] = {
      /* Whitespace / control. */
      {"Enter", GHOST_kKeyEnter},
      {"Escape", GHOST_kKeyEsc},
      {"Backspace", GHOST_kKeyBackSpace},
      {"Tab", GHOST_kKeyTab},
      {"Space", GHOST_kKeySpace},

      /* Editing / navigation. */
      {"Delete", GHOST_kKeyDelete},
      {"Insert", GHOST_kKeyInsert},
      {"Home", GHOST_kKeyHome},
      {"End", GHOST_kKeyEnd},
      {"PageUp", GHOST_kKeyUpPage},
      {"PageDown", GHOST_kKeyDownPage},
      {"ArrowLeft", GHOST_kKeyLeftArrow},
      {"ArrowRight", GHOST_kKeyRightArrow},
      {"ArrowUp", GHOST_kKeyUpArrow},
      {"ArrowDown", GHOST_kKeyDownArrow},

      /* Locks / system. */
      {"CapsLock", GHOST_kKeyCapsLock},
      {"NumLock", GHOST_kKeyNumLock},
      {"ScrollLock", GHOST_kKeyScrollLock},
      {"PrintScreen", GHOST_kKeyPrintScreen},
      {"Pause", GHOST_kKeyPause},
      {"ContextMenu", GHOST_kKeyApp},

      /* Modifiers (left/right distinguished — this is why we use `code`). */
      {"ShiftLeft", GHOST_kKeyLeftShift},
      {"ShiftRight", GHOST_kKeyRightShift},
      {"ControlLeft", GHOST_kKeyLeftControl},
      {"ControlRight", GHOST_kKeyRightControl},
      {"AltLeft", GHOST_kKeyLeftAlt},
      {"AltRight", GHOST_kKeyRightAlt},
      {"MetaLeft", GHOST_kKeyLeftOS},
      {"MetaRight", GHOST_kKeyRightOS},
      {"OSLeft", GHOST_kKeyLeftOS},
      {"OSRight", GHOST_kKeyRightOS},

      /* Punctuation (physical positions on a US layout). */
      {"Minus", GHOST_kKeyMinus},
      {"Equal", GHOST_kKeyEqual},
      {"BracketLeft", GHOST_kKeyLeftBracket},
      {"BracketRight", GHOST_kKeyRightBracket},
      {"Backslash", GHOST_kKeyBackslash},
      {"Semicolon", GHOST_kKeySemicolon},
      {"Quote", GHOST_kKeyQuote},
      {"Backquote", GHOST_kKeyAccentGrave},
      {"Comma", GHOST_kKeyComma},
      {"Period", GHOST_kKeyPeriod},
      {"Slash", GHOST_kKeySlash},
      {"IntlBackslash", GHOST_kKeyGrLess},

      /* Numpad non-digit keys. */
      {"NumpadDecimal", GHOST_kKeyNumpadPeriod},
      {"NumpadEnter", GHOST_kKeyNumpadEnter},
      {"NumpadAdd", GHOST_kKeyNumpadPlus},
      {"NumpadSubtract", GHOST_kKeyNumpadMinus},
      {"NumpadMultiply", GHOST_kKeyNumpadAsterisk},
      {"NumpadDivide", GHOST_kKeyNumpadSlash},
  };

  for (const Entry &e : table) {
    if (std::strcmp(code, e.code) == 0) {
      return e.key;
    }
  }
  return GHOST_kKeyUnknown;
}

/**
 * Copy the printable text produced by a key press into a GHOST utf8 buffer.
 * `key` is `KeyboardEvent.key`; we only accept it when it is a single printable
 * grapheme (length 1..4 bytes and NOT a named key like "Shift"/"ArrowLeft"). Named
 * keys have multi-char ASCII names, so we reject any `key` whose first byte is an
 * ASCII letter AND whose length is > 1 (heuristic: printable symbols/digits are
 * length 1; multi-byte UTF-8 graphemes have a high first byte).
 */
static inline void ghost_web_utf8_from_key(const char *key, char out_utf8[6])
{
  out_utf8[0] = '\0';
  if (key == nullptr) {
    return;
  }
  const size_t len = std::strlen(key);
  if (len == 0 || len > 4) {
    /* Empty, or a named key ("Enter", "Shift", "ArrowLeft", ...). */
    return;
  }
  const unsigned char c0 = (unsigned char)key[0];
  if (len > 1 && c0 < 0x80) {
    /* Multi-char ASCII => a named key, not text. */
    return;
  }
  std::memcpy(out_utf8, key, len);
  if (len < 6) {
    out_utf8[len] = '\0';
  }
}
