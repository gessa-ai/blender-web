#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-3.0-or-later
#
# stage_pack.py - repackage a monolithic emscripten --preload-file payload into a
# staged pair, entirely in the DEPLOY bundle (never touches the build tree).
#
# Input  (read-only): a built blender_browser.{js,data} (monolith preload).
# Output (bundle):    blender_browser.js  (glue with the baked manifest rewritten
#                         to STAGE-0 real files + zero-length placeholders for every
#                         deferred file, so the preload creates the FULL directory
#                         tree - post-boot mkdir is impossible under the 0555 /bw
#                         mount, but writing files into existing dirs works),
#                     blender_browser.data (= stage-0 bytes only; the baked preload
#                         fetches THIS, so boot blocks on stage-0 alone),
#                     stage1.data + stage1-manifest.json (deferred bytes, streamed
#                         in post-first-pixels by stage1-loader.js via FS.writeFile).
#
# The .data format is a bare byte concatenation; each manifest entry is a
# [start,end) slice. We re-slice the monolith into two concatenations and rewrite
# the offsets. No emscripten relink; the glue is edited as a bundle artifact.
#
# Classification (oracle-validated in notes/m8-staged-loading.md sections 2-3):
#   DROP  - never needed at runtime: __pycache__/.pyc (already pruned upstream),
#           pip .whl.  Omitted from both stages.
#   DEFER - not touched at English --factory-startup boot (-> stage-1):
#           dead stdlib modules, non-enabled addons (rigify, ...), factory-unselected
#           application templates, NumPy (not imported before first pixels), boot-cold
#           Python codecs, file-format implementation modules outside the enabled add-ons'
#           boot registration closure, developer/help/template/test scripts and inactive
#           presets (keep the active Blender keymap), CJK/intl fonts (keep Inter +
#           DejaVuSansMono), non-default colormanagement LUTs (keep config.ocio + the
#           default AgX display path), build-time/compiled-in source assets and external
#           StudioLight images.
#           [--defer-datafiles]
#   KEEP  - everything else (-> stage-0).
import argparse
from decimal import Decimal, InvalidOperation
import json
import os
import re
import sys

RE_ENTRY = re.compile(
    r'\{filename:"((?:[^"\\]|\\.)*)",start:([0-9]+(?:[eE]\+?[0-9]+)?),'
    r'end:([0-9]+(?:[eE]\+?[0-9]+)?)\}'
)

# --- oracle-validated partition sets (notes/m8-staged-loading.md sec 2-3) --------
DEAD_STDLIB = (
    "idlelib/", "tkinter/", "turtledemo/", "turtle.py", "ensurepip/", "pydoc_data/",
    "lib2to3/", "venv/", "/test/", "distutils/", "antigravity.py", "this.py",
    "__phello__", "zoneinfo/", "wsgiref/", "xmlrpc/", "asyncio/", "concurrent/",
    "curses/", "unittest/", "sqlite3/", "dbm/", "pydoc.py", "doctest.py", "pdb.py",
    "profile.py", "cProfile.py", "smtplib.py", "ftplib.py", "poplib.py", "imaplib.py",
    "mailbox.py", "cgitb.py",
)
# Addons whose register() runs at --factory-startup (native oracle) MUST be stage-0.
STAGE0_ADDONS = (
    "bl_pkg", "cycles", "io_scene_fbx", "io_scene_gltf2", "io_anim_bvh", "pose_library",
    "io_curve_svg", "io_mesh_uv_layout",
)
# Native factory-startup and a real windowed CAPTURE boot agree on this exact
# registration/UI closure for the enabled file-format add-ons. Their import/export
# implementations are first used by the post-Stage-1 M7 operator lane, so keeping
# whole add-on trees in Stage 0 duplicates cold Python on the first-pixel wire.
STAGED_FORMAT_ADDONS = frozenset({
    "io_anim_bvh", "io_curve_svg", "io_mesh_uv_layout", "io_scene_fbx", "io_scene_gltf2",
})
STAGE0_FORMAT_BOOT_FILES = frozenset({
    "io_anim_bvh/__init__.py",
    "io_curve_svg/__init__.py",
    "io_mesh_uv_layout/__init__.py",
    "io_scene_fbx/__init__.py",
    "io_scene_gltf2/__init__.py",
    "io_scene_gltf2/blender/__init__.py",
    "io_scene_gltf2/blender/com/gltf2_blender_ui.py",
    "io_scene_gltf2/blender/com/material_helpers.py",
})
INTL_FONT_KEEP = ("Inter.woff2", "DejaVuSansMono.woff2")
CM_LUT_KEEP = ("config.ocio", "AgX_Base_sRGB.cube", "Guard_Rail_Shaper_EOTF.spi1d",
               "AgX_False_Color.spi1d")
# Pinned native factory startup and the exact windowed CAPTURE generation agree on
# this codec-source closure. The registry, aliases, IDNA, and UTF-8 paths must be
# available before first pixels; legacy/locale-specific codecs can arrive with
# Stage 1 and retain exact support after restoration.
STAGE0_ENCODING_FILES = frozenset({
    "__init__.py", "aliases.py", "idna.py", "utf_8.py", "utf_8_sig.py",
})
# Exact browser-cold Python sources measured after the stable WM loop in the
# CAPTURE generation, then pruned by a zero-error staged/monolith A/B. Keep this
# an allowlisted DEFER set: an unmeasured new source stays in Stage 0. Trusted
# input and representative lazy imports are exercised by
# verify_python_runtime_stage0.mjs before/after Stage 1.
BOOT_COLD_PYTHON_SOURCES = frozenset("""
__hello__.py
_aix_support.py
_android_support.py
_apple_support.py
_ios_support.py
_markupbase.py
_osx_support.py
_py_abc.py
_pydatetime.py
_pydecimal.py
_pyio.py
_pylong.py
_pyrepl/__init__.py
_pyrepl/__main__.py
_pyrepl/_minimal_curses.py
_pyrepl/_threading_handler.py
_pyrepl/base_eventqueue.py
_pyrepl/commands.py
_pyrepl/completing_reader.py
_pyrepl/console.py
_pyrepl/curses.py
_pyrepl/fancy_termios.py
_pyrepl/historical_reader.py
_pyrepl/input.py
_pyrepl/keymap.py
_pyrepl/main.py
_pyrepl/pager.py
_pyrepl/reader.py
_pyrepl/readline.py
_pyrepl/simple_interact.py
_pyrepl/trace.py
_pyrepl/types.py
_pyrepl/unix_console.py
_pyrepl/unix_eventqueue.py
_pyrepl/utils.py
_pyrepl/windows_console.py
_pyrepl/windows_eventqueue.py
_strptime.py
_sysconfigdata__emscripten_wasm32-emscripten.py
_threading_local.py
bdb.py
bz2.py
cmd.py
code.py
codeop.py
colorsys.py
compileall.py
configparser.py
contextvars.py
csv.py
ctypes/__init__.py
ctypes/_aix.py
ctypes/_endian.py
ctypes/macholib/__init__.py
ctypes/macholib/dyld.py
ctypes/macholib/dylib.py
ctypes/macholib/framework.py
ctypes/util.py
ctypes/wintypes.py
decimal.py
difflib.py
email/_header_value_parser.py
email/contentmanager.py
email/generator.py
email/headerregistry.py
email/mime/__init__.py
email/mime/application.py
email/mime/audio.py
email/mime/base.py
email/mime/image.py
email/mime/message.py
email/mime/multipart.py
email/mime/nonmultipart.py
email/mime/text.py
email/policy.py
filecmp.py
fileinput.py
fractions.py
getopt.py
getpass.py
graphlib.py
gzip.py
html/__init__.py
html/entities.py
html/parser.py
http/server.py
importlib/metadata/_adapters.py
importlib/metadata/_text.py
importlib/metadata/diagnose.py
importlib/resources/simple.py
importlib/simple.py
json/tool.py
logging/config.py
logging/handlers.py
lzma.py
modulefinder.py
multiprocessing/dummy/__init__.py
multiprocessing/dummy/connection.py
multiprocessing/forkserver.py
multiprocessing/heap.py
multiprocessing/managers.py
multiprocessing/pool.py
multiprocessing/popen_fork.py
multiprocessing/popen_forkserver.py
multiprocessing/popen_spawn_posix.py
multiprocessing/popen_spawn_win32.py
multiprocessing/queues.py
multiprocessing/resource_sharer.py
multiprocessing/resource_tracker.py
multiprocessing/shared_memory.py
multiprocessing/sharedctypes.py
multiprocessing/spawn.py
netrc.py
nturl2path.py
numbers.py
optparse.py
pickletools.py
pkgutil.py
plistlib.py
pprint.py
pstats.py
pty.py
py_compile.py
pyclbr.py
rlcompleter.py
runpy.py
sched.py
secrets.py
shelve.py
shlex.py
site-packages/cattr/__init__.py
site-packages/cattr/converters.py
site-packages/cattr/disambiguators.py
site-packages/cattr/dispatch.py
site-packages/cattr/errors.py
site-packages/cattr/gen.py
site-packages/cattr/preconf/__init__.py
site-packages/cattr/preconf/bson.py
site-packages/cattr/preconf/json.py
site-packages/cattr/preconf/msgpack.py
site-packages/cattr/preconf/orjson.py
site-packages/cattr/preconf/pyyaml.py
site-packages/cattr/preconf/tomlkit.py
site-packages/cattr/preconf/ujson.py
site-packages/cattrs/preconf/bson.py
site-packages/cattrs/preconf/cbor2.py
site-packages/cattrs/preconf/msgpack.py
site-packages/cattrs/preconf/msgspec.py
site-packages/cattrs/preconf/orjson.py
site-packages/cattrs/preconf/pyyaml.py
site-packages/cattrs/preconf/tomlkit.py
site-packages/cattrs/preconf/ujson.py
site-packages/certifi/__main__.py
site-packages/charset_normalizer/__main__.py
site-packages/charset_normalizer/cli/__init__.py
site-packages/charset_normalizer/cli/__main__.py
site-packages/idna/codec.py
site-packages/idna/compat.py
site-packages/idna/uts46data.py
site-packages/requests/help.py
site-packages/urllib3/contrib/socks.py
site-packages/urllib3/http2/connection.py
site-packages/urllib3/util/ssltransport.py
socketserver.py
sre_compile.py
sre_constants.py
sre_parse.py
statistics.py
symtable.py
sysconfig/__init__.py
sysconfig/__main__.py
tabnanny.py
tarfile.py
timeit.py
trace.py
tty.py
urllib/robotparser.py
wave.py
webbrowser.py
xml/__init__.py
xml/dom/NodeFilter.py
xml/dom/__init__.py
xml/dom/domreg.py
xml/dom/expatbuilder.py
xml/dom/minicompat.py
xml/dom/minidom.py
xml/dom/pulldom.py
xml/dom/xmlbuilder.py
xml/etree/ElementInclude.py
xml/etree/ElementPath.py
xml/etree/ElementTree.py
xml/etree/__init__.py
xml/etree/cElementTree.py
xml/parsers/__init__.py
xml/parsers/expat.py
xml/sax/__init__.py
xml/sax/_exceptions.py
xml/sax/expatreader.py
xml/sax/handler.py
xml/sax/saxutils.py
xml/sax/xmlreader.py
zipapp.py
zipfile/__main__.py
""".split())
# These source trees serve authoring, help, translation, test, or feature-deferred
# workflows. Neither pinned native factory startup nor the exact windowed CAPTURE
# product imports them before the stable main loop. Keep them byte-exact in Stage 1.
BOOT_COLD_SUPPORT_PREFIXES = (
    "/bw/scripts/addons_core/bl_pkg/tests/",
    "/bw/scripts/freestyle/",
    "/bw/scripts/modules/_bl_i18n_utils/",
    "/bw/scripts/templates_osl/",
    "/bw/scripts/templates_py/",
    "/bw/scripts/templates_toml/",
)
BOOT_COLD_SUPPORT_FILES = frozenset({
    "/bw/scripts/modules/_rna_manual_reference.py",
})
# Presets are selected on demand. Factory startup executes this exact active
# Blender-keymap pair indirectly (so sys.modules alone cannot discover it); all
# alternate keymaps and operator/data presets can arrive after first pixels.
STAGE0_PRESET_FILES = frozenset({
    "keyconfig/Blender.py",
    "keyconfig/keymap_data/blender_default.py",
})


def in_py(fn):
    return "/bw/python/lib/python3.13" in fn


def classify(fn, defer_datafiles):
    """Return 'drop' | 'defer' | 'keep'."""
    # DROP: never needed at runtime.
    if "__pycache__" in fn or fn.endswith(".pyc"):
        return "drop"
    if fn.endswith(".whl"):
        return "drop"
    # DEFER: python stdlib not imported at boot.
    if in_py(fn) and any(d in fn for d in DEAD_STDLIB):
        return "defer"
    # DEFER: Python ships 123 source codecs, but factory startup loads only the
    # five-file registry/UTF-8 closure above. Stage 1 restores all other codecs
    # before post-startup IO and scripting coverage.
    encoding_prefix = "/bw/python/lib/python3.13/encodings/"
    if fn.startswith(encoding_prefix) and fn[len(encoding_prefix):] not in STAGE0_ENCODING_FILES:
        return "defer"
    # DEFER: exact Python sources absent from the measured browser boot closure.
    # This is an explicit set rather than a generated complement so any new or
    # renamed source fails safe into Stage 0 until it receives runtime evidence.
    python_prefix = "/bw/python/lib/python3.13/"
    if fn.startswith(python_prefix) and fn[len(python_prefix):] in BOOT_COLD_PYTHON_SOURCES:
        return "defer"
    # DEFER: the real windowed product and pinned native factory startup both import
    # zero NumPy modules before the first stable WM state. Stage 1 restores the whole
    # package before IO/operator coverage, avoiding a partial-package boundary.
    if "/site-packages/numpy/" in fn:
        return "defer"
    # DEFER: OpenUSD schema/plugin resources are consumed only when a USD
    # import/export operator runs. The operator lane is a post-Stage-1 M7 gate;
    # keeping these out of the first-pixel payload is both safe and measurable.
    if fn.startswith("/usd/"):
        return "defer"
    # DEFER: add-ons not enabled at --factory-startup, plus enabled file-format
    # implementation modules outside the measured registration/UI boot closure.
    addon_prefix = "/bw/scripts/addons_core/"
    if fn.startswith(addon_prefix):
        relative = fn[len(addon_prefix):]
        addon = relative.partition("/")[0]
        if addon not in STAGE0_ADDONS:
            return "defer"
        if addon in STAGED_FORMAT_ADDONS and relative not in STAGE0_FORMAT_BOOT_FILES:
            return "defer"
    # DEFER: factory startup has no selected application template. These alternate
    # startup files are needed only after the user chooses File > New, by which
    # time the post-first-pixel Stage-1 stream has restored their real bytes.
    if "/bw/scripts/startup/bl_app_templates_system/" in fn:
        return "defer"
    # DEFER: measured boot-cold support sources and inactive presets. The active
    # default keymap remains complete so Stage 0 is genuinely interactive.
    if fn.startswith(BOOT_COLD_SUPPORT_PREFIXES) or fn in BOOT_COLD_SUPPORT_FILES:
        return "defer"
    preset_prefix = "/bw/scripts/presets/"
    if fn.startswith(preset_prefix) and fn[len(preset_prefix):] not in STAGE0_PRESET_FILES:
        return "defer"
    if defer_datafiles:
        # DEFER: sources that Blender's build converts into C/object data before
        # linking. The runtime consumes those compiled copies; preloading the
        # original SVG/font/theme and generator inputs duplicates them on the
        # first-pixel wire. Stage 1 retains the exact source bytes for inspection.
        if fn.startswith((
            "/bw/datafiles/icons_svg/",
            "/bw/datafiles/cursors/",
            "/bw/datafiles/userdef/",
        )) or fn in {
            "/bw/datafiles/DejaVuSans-Lite.sfd.bz2",
            "/bw/datafiles/bfont.pfb",
            "/bw/datafiles/blender_icons_geom.py",
            "/bw/datafiles/blender_icons_geom_update.py",
            "/bw/datafiles/ctodata.py",
        }:
            return "defer"
        # DEFER: source assets compiled into Blender (preview*.blend and splash.png),
        # authoring-only splash_template.xcf, and toolbar.blend (a build-time input
        # to blender_icons_geom_update.py). Runtime icon output remains Stage 0.
        if "/datafiles/icons_blend/" in fn:
            return "defer"
        if any(suffix in fn for suffix in (
            "/datafiles/preview.blend",
            "/datafiles/preview_grease_pencil.blend",
            "/datafiles/splash.png",
            "/datafiles/splash_template.xcf",
        )):
            return "defer"
        # Solid Workbench's factory-startup selection names an external `.sl`
        # preset even though the light implementation also has an internal
        # fallback. Keep the tiny text presets so the first frame cannot select a
        # zero-length placeholder and shade black. World/matcap images are lazy
        # choices and can arrive after first pixels with the rest of Stage 1.
        if "/datafiles/studiolights/" in fn and not fn.endswith(".sl"):
            return "defer"
        # DEFER: non-Latin / CJK fonts (English UI never demands them at boot).
        if "/datafiles/fonts/" in fn and not any(k in fn for k in INTL_FONT_KEEP):
            return "defer"
        # DEFER: colormanagement display LUTs except the default AgX-sRGB path.
        if "/datafiles/colormanagement/" in fn and (fn.endswith(".cube") or fn.endswith(".spi1d")) \
           and not any(k in fn for k in CM_LUT_KEEP):
            return "defer"
        # DEFER: i18n message catalogs (WITH_INTERNATIONAL, r45). English is the source
        # language and loads no .mo at boot; a non-English catalog is only read when the
        # user switches language, so the 49 blender.mo ride stage-1 with the CJK fonts. The
        # small `datafiles/locale/languages` index is NOT matched here and falls through to
        # KEEP (stage-0) so the language menu is populated at BLT_lang_init.
        if "/datafiles/locale/" in fn and fn.endswith("/LC_MESSAGES/blender.mo"):
            return "defer"
    return "keep"


def parse_manifest(glue_text):
    i = glue_text.find("loadPackage({files:[")
    if i < 0:
        sys.exit("stage_pack: FATAL: loadPackage({files:[ not found in glue")
    # Find the enclosing loadPackage({ ... }) argument object.
    open_brace = glue_text.find("{", i + len("loadPackage("))
    # remote_package_size marks the tail of the metadata object.
    m = re.search(r"\],remote_package_size:(\d+)\}\)", glue_text[i:])
    if not m:
        sys.exit("stage_pack: FATAL: remote_package_size tail not found")
    meta_start = open_brace
    meta_end = i + m.end()  # position just past the closing '})'
    meta_text = glue_text[meta_start:meta_end]
    def js_integer(value):
        try:
            parsed = Decimal(value)
        except InvalidOperation:
            sys.exit(f"stage_pack: FATAL: invalid JS integer literal {value!r}")
        integral = parsed.to_integral_value()
        if parsed != integral or integral < 0:
            sys.exit(f"stage_pack: FATAL: non-integer JS range literal {value!r}")
        return int(integral)

    entries = [(fn, js_integer(s), js_integer(e)) for fn, s, e in RE_ENTRY.findall(meta_text)]
    declared_entries = meta_text.count('{filename:"')
    if declared_entries != len(entries):
        sys.exit(
            f"stage_pack: FATAL: parsed {len(entries)} of {declared_entries} manifest entries"
        )
    remote_size = int(m.group(1))
    return meta_start, meta_end, entries, remote_size


def validate_source_manifest(entries, remote_size, blob_size):
    if remote_size != blob_size:
        sys.exit(
            f"stage_pack: FATAL: remote_package_size {remote_size} != data bytes {blob_size}"
        )
    if not entries:
        sys.exit("stage_pack: FATAL: preload manifest contains no entries")

    seen = set()
    intervals = []
    for index, (filename, start, end) in enumerate(entries):
        if not filename.startswith("/") or "\\" in filename or "\0" in filename:
            sys.exit(f"stage_pack: FATAL: unsafe manifest path at {index}: {filename!r}")
        if filename in seen:
            sys.exit(f"stage_pack: FATAL: duplicate manifest path: {filename}")
        seen.add(filename)
        if not (0 <= start <= end <= blob_size):
            sys.exit(
                f"stage_pack: FATAL: invalid range [{start},{end})/{blob_size} for {filename}"
            )
        intervals.append((start, end, filename))

    cursor = 0
    for start, end, filename in sorted(intervals):
        if start != cursor:
            relation = "overlap" if start < cursor else "gap"
            sys.exit(
                f"stage_pack: FATAL: source interval {relation}: expected {cursor}, "
                f"got [{start},{end}) for {filename}"
            )
        cursor = end
    if cursor != blob_size:
        sys.exit(f"stage_pack: FATAL: source coverage ends at {cursor}, expected {blob_size}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bin", required=True, help="dir with monolith blender_browser.{js,data}")
    ap.add_argument("--out", required=True, help="bundle bin/ output dir")
    ap.add_argument("--defer-datafiles", dest="defer_datafiles", action="store_true", default=True)
    ap.add_argument("--no-defer-datafiles", dest="defer_datafiles", action="store_false")
    ap.add_argument("--dry-run", action="store_true", help="print stats only")
    args = ap.parse_args()

    glue_path = os.path.join(args.bin, "blender_browser.js")
    data_path = os.path.join(args.bin, "blender_browser.data")
    glue = open(glue_path).read()
    meta_start, meta_end, entries, remote_size = parse_manifest(glue)
    blob = open(data_path, "rb").read()
    validate_source_manifest(entries, remote_size, len(blob))

    buckets = {"keep": [], "defer": [], "drop": []}
    for fn, s, e in entries:
        buckets[classify(fn, args.defer_datafiles)].append((fn, s, e))

    def total(b):
        return sum(e - s for _, s, e in buckets[b])

    print(f"entries={len(entries)}  data={len(blob):,} bytes")
    for b in ("keep", "defer", "drop"):
        n = len(buckets[b]); t = total(b)
        print(f"  {b:5s}: {n:5d} files  {t:12,d} bytes  ({t/1048576:7.2f} MiB)")
    stage0_bytes = total("keep")
    classified_bytes = sum(total(bucket) for bucket in ("keep", "defer", "drop"))
    if classified_bytes != len(blob):
        sys.exit(
            f"stage_pack: FATAL: classified coverage {classified_bytes} != data bytes {len(blob)}"
        )
    print(f"  => stage0.data {stage0_bytes/1048576:.2f} MiB   stage1.data {total('defer')/1048576:.2f} MiB")

    if args.dry_run:
        # show the largest DEFER contributors for a sanity check
        big = sorted(buckets["defer"], key=lambda x: x[2] - x[1], reverse=True)[:12]
        print("  top DEFER files:")
        for fn, s, e in big:
            print(f"    {(e-s):10,d}  {fn}")
        return

    os.makedirs(args.out, exist_ok=True)

    # --- build stage0.data + new KEEP offsets, and stage1.data + stage1 manifest ---
    stage0 = bytearray()
    stage1 = bytearray()
    new_entries = []          # for the rewritten baked manifest (stage-0 + placeholders)
    stage1_manifest = []      # for stage1-loader.js
    for fn, s, e in entries:
        b = classify(fn, args.defer_datafiles)
        if b == "keep":
            start = len(stage0)
            stage0 += blob[s:e]
            new_entries.append((fn, start, len(stage0)))
        elif b == "defer":
            start = len(stage1)
            stage1 += blob[s:e]
            stage1_manifest.append({"filename": fn, "start": start, "end": len(stage1)})
            # zero-length placeholder in stage-0 so the DIRECTORY TREE is created at
            # preload (post-boot mkdir is impossible); real bytes arrive via
            # FS.writeFile from stage1-loader.js.
            new_entries.append((fn, 0, 0))
        # drop: omit entirely

    # rewrite the baked metadata object in the glue
    files_js = ",".join(
        '{filename:"%s",start:%d,end:%d}' % (fn, s, e) for fn, s, e in new_entries
    )
    new_meta = "{files:[" + files_js + "],remote_package_size:%d}" % len(stage0)
    # glue[meta_start:meta_end] spanned the object '{...}' PLUS loadPackage's ')'.
    # new_meta is the complete replacement object; re-add ONLY the ')'.
    new_glue = glue[:meta_start] + new_meta + ")" + glue[meta_end:]

    with open(os.path.join(args.out, "blender_browser.js"), "w") as f:
        f.write(new_glue)
    with open(os.path.join(args.out, "blender_browser.data"), "wb") as f:
        f.write(stage0)
    with open(os.path.join(args.out, "stage1.data"), "wb") as f:
        f.write(stage1)
    with open(os.path.join(args.out, "stage1-manifest.json"), "w") as f:
        json.dump({"total_bytes": len(stage1), "files": stage1_manifest}, f)

    print(f"stage_pack: wrote stage-0 glue+data ({len(stage0):,} B), "
          f"stage1.data ({len(stage1):,} B, {len(stage1_manifest)} files), manifest")


if __name__ == "__main__":
    main()
