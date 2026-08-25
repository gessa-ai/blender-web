// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: GPL-2.0-or-later

#include <cstdio>

#include <emscripten/emscripten.h>
#include <emscripten/threading.h>

static void publish_title(const char *title)
{
  MAIN_THREAD_EM_ASM(
      {
        if (typeof document === "undefined") {
          throw new Error("missing document on main runtime thread");
        }
        document.title = UTF8ToString($0);
        globalThis.__bwTitleRanOnPthread =
            typeof ENVIRONMENT_IS_PTHREAD !== "undefined" && ENVIRONMENT_IS_PTHREAD;
      },
      title);
}

int main()
{
  if (emscripten_is_main_runtime_thread()) {
    std::fprintf(stderr, "TITLE_MAIN_THREAD_PROBE FAIL main-not-proxied\n");
    return 2;
  }

  const char *title = "Cube · αβ · blender-web";
  publish_title(title);
  const int unicode_ok = MAIN_THREAD_EM_ASM_INT(
      { return document.title === UTF8ToString($0) && !globalThis.__bwTitleRanOnPthread; }, title);
  publish_title("");
  const int empty_ok = MAIN_THREAD_EM_ASM_INT(
      { return document.title === "" && !globalThis.__bwTitleRanOnPthread; });
  if (!unicode_ok || !empty_ok) {
    std::fprintf(stderr, "TITLE_MAIN_THREAD_PROBE FAIL title-mismatch\n");
    return 3;
  }

  MAIN_THREAD_EM_ASM(
      {
        console.log(
            "TITLE_MAIN_THREAD_PROBE PASS worker=proxied values=unicode,empty unicode=preserved");
      });
  return 0;
}
