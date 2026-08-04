<!--
SPDX-FileCopyrightText: 2026 blender-web contributors
SPDX-License-Identifier: CC0-1.0
-->

# M4.pre2 — GHOST-web recon (virtual surface, events, keymap, link set)

Read-only recon at the pin (`fbe6228777e7`) for the custom `GHOST_SystemWeb` /
`GHOST_WindowWeb`. Reference minimal implementations: `GHOST_SystemHeadless.hh`
(system) and `GHOST_WindowNULL.hh` (window) — every method they `override` with a
body is exactly the concrete surface a back-end must supply.

## 1. Virtual surface — pure vs defaulted

The interfaces (`GHOST_ISystem` / `GHOST_IWindow`) are almost entirely pure; the
partial bases (`GHOST_System` / `GHOST_Window`) implement the platform-independent
bulk and re-declare a small protected slice as pure for the back-end.

| interface | pure virtuals | defaulted by partial base | concrete back-end MUST implement |
|---|---|---|---|
| `GHOST_ISystem` (GHOST_ISystem.hh) | 40 | 21 in `GHOST_System` | **19** (= the `override` set in `GHOST_SystemHeadless.hh`) |
| `GHOST_IWindow` (GHOST_IWindow.hh) | 46 | 24 in `GHOST_Window` | **~22** public + **4** `GHOST_Window` protected pures |

### System — the 19 a concrete system implements (GHOST_SystemHeadless.hh:36-245)
`processEvents`, `setConsoleWindowState`, `getModifierKeys(GHOST_ModifierKeys&) const`,
`getButtons(GHOST_Buttons&) const`, `getCapabilities() const`, `getClipboard(bool) const`,
`putClipboard(const char*,bool) const`, `getMilliSeconds() const`, `getNumDisplays() const`,
`getCursorPosition(int32_t&,int32_t&) const`, `setCursorPosition(int32_t,int32_t)`,
`getMainDisplayDimensions(uint32_t&,uint32_t&) const`, `getAllDisplayDimensions(...) const`,
`createOffscreenContext(GHOST_GPUSettings)`, `disposeContext(GHOST_IContext*)`, `init()`,
`createWindow(...)`, `getWindowUnderCursor(int32_t,int32_t)`. (`init()`/`getMilliSeconds()`
have base defaults but are conventionally overridden.)
`GHOST_System::init()` (GHOST_System.cc:305) constructs the timer/window/**event**
managers — a concrete `init()` MUST chain `GHOST_System::init()` (we do).

### Window — the set a concrete window implements (GHOST_WindowNULL.hh:20-147)
Public (IWindow pures GHOST_Window leaves open): `getValid`, `setTitle`, `getTitle`,
`getWindowBounds`, `getClientBounds`, `setClientWidth/Height/Size`, `screenToClient`,
`clientToScreen`, `getState`, `setState`, `setOrder`, `swapBufferRelease`,
`activateDrawingContext`, `invalidate`, `hasCursorShape`.
Protected pures added by `GHOST_Window` (GHOST_Window.hh:284-309): `newDrawingContext`,
`setWindowCursorVisibility`, `setWindowCursorShape`, `setWindowCustomCursorShape`
(+ `setWindowCursorGrab`). `GHOST_Window` DEFAULTS the rest (`setPath`, `getDPIHint`,
`getNativePixelSize`, cursor-generator/bitmap, IME no-ops, progress bar, user-data,
drawing-context-type, swap-interval, `swapBufferAcquire`, decoration styles, ...) — we
override `getDPIHint` only (devicePixelRatio HiDPI).

## 2. Event types Blender's WM consumes (GHOST_Types.hh:308-384) and our mapping

| GHOST event | data struct | HTML5 source | notes |
|---|---|---|---|
| `GHOST_kEventCursorMove` | `GHOST_TEventCursorData{x,y,tablet}` | `mousemove` `targetX/Y` | canvas-relative |
| `GHOST_kEventButtonDown/Up` | `GHOST_TEventButtonData{button,tablet}` | `mousedown/up` `button` | 0→Left,1→Middle,2→Right,3→B4,4→B5 |
| `GHOST_kEventWheel` | `GHOST_TEventWheelData{axis,value}` | `wheel` `deltaX/Y` | value ±1/notch; deltaY>0→−1 (up=+1) |
| `GHOST_kEventKeyDown/Up` | `GHOST_TEventKeyData{key,utf8_buf[6],is_repeat}` | `keydown/up` `code`+`key`+`repeat` | key from `code`; utf8 from `key` |
| `GHOST_kEventWindowSize` | (none) | `resize` (window) | WM re-queries `getClientBounds` |
| `GHOST_kEventWindowActivate/Deactivate` | (none) | `focus`/`blur` (canvas) | |

Event ctors (all `push`ed via `GHOST_System::pushEvent(std::unique_ptr<const GHOST_IEvent>)`,
public — GHOST_System.hh:224): `GHOST_EventCursor(msec,type,win,x,y,tablet)`,
`GHOST_EventButton(msec,type,win,button,tablet)`, `GHOST_EventWheel(msec,win,axis,value)`,
`GHOST_EventKey(msec,type,win,key,is_repeat,utf8[6])`, base `GHOST_Event(msec,type,win)`.

## 3. Keyboard map — HTML5 `KeyboardEvent.code` → `GHOST_TKey`

Keyed on `code` (physical position, layout-independent — GHOST's key-code contract),
NOT `key`; the produced character rides in `utf8_buf` (from `key`). Full table in
`platform_web/ghost/GHOST_KeyMapWeb.hh`. Coverage:

| group | codes | GHOST_TKey |
|---|---|---|
| letters | `KeyA`..`KeyZ` | `GHOST_kKeyA`+ (by `code[3]`) |
| digits | `Digit0`..`Digit9` | `GHOST_kKey0`+ |
| numpad | `Numpad0..9`, `NumpadDecimal/Enter/Add/Subtract/Multiply/Divide` | `GHOST_kKeyNumpad*` |
| function | `F1`..`F24` | `GHOST_kKeyF1`+ |
| arrows/nav | `Arrow*`, `Home/End/PageUp/PageDown/Insert/Delete` | mapped (PageUp→`UpPage`) |
| modifiers | `Shift/Control/Alt/Meta` `Left`/`Right` | left/right distinguished |
| locks/system | `CapsLock/NumLock/ScrollLock/PrintScreen/Pause/ContextMenu` | ContextMenu→`App` |
| punctuation | `Minus/Equal/Bracket*/Backslash/Semicolon/Quote/Backquote/Comma/Period/Slash/IntlBackslash` | Backquote→`AccentGrave`, IntlBackslash→`GrLess` |
| whitespace | `Enter/Escape/Backspace/Tab/Space` | |

**Deferred (documented):** dead-keys / IME composition (`compositionstart/update/end`,
`GHOST_kEventImeComposition*`), matching GOAL.md's SDL IME-gap rationale — we don't
advertise `GHOST_kCapabilityInputIME`. Layout note: `code` is physical (US-QWERTY
positions); the localized character is always correct because it comes from `key`.

## 4. Standalone link dependency set (verified empirically)

To link a concrete GHOST system+window with NO X11/SDL/Cocoa/GL/Vulkan, the minimal
real base `.cc` set (`upstream/intern/ghost/intern/`) is:

| file | why |
|---|---|
| `GHOST_System.cc` | base; init() builds the managers |
| `GHOST_Window.cc` | base; installs a default `GHOST_ContextNone` |
| `GHOST_EventManager.cc` | queue + consumer dispatch |
| `GHOST_WindowManager.cc` | `addWindow` |
| `GHOST_TimerManager.cc` | built by `GHOST_System::init()` |
| `GHOST_ModifierKeys.cc`, `GHOST_Buttons.cc` | tracked-state types |
| `GHOST_Context.cc`, `GHOST_ContextNone.cc` | `GHOST_Window` default context (`new GHOST_ContextNone`) |
| `GHOST_Rect.cc` | **vtable for GHOST_Rect** (not header-only — first link error) |
| guardedalloc `mallocn*.cc`, `memory_usage.cc`, `leak_detector.cc` | `GHOST_Types.hh` pulls `MEM_guardedalloc.h` (`MEM_CXX_CLASS_ALLOC_FUNCS`) |

Include paths: `platform_web/ghost`, `upstream/intern/ghost`, `.../ghost/intern`,
`upstream/intern/guardedalloc`, `upstream/intern/atomic`.
**NOT** needed: `GHOST_ISystem.cc` (we instantiate `GHOST_SystemWeb` directly, not via
`createSystem()`; its `#ifdef` platform body would drag in X11/SDL); no `CLG_log`/clog
(only `GHOST_ISystem.cc` used it); no MEM path beyond guardedalloc; no GL/epoxy.
