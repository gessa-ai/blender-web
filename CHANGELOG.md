# Changelog

All notable public releases. Internal engineering history is retained
privately; each release lists what is user-visible.

## v0.1.1 — 2026-08-27

Hardware-verified bugfix release. Every item below was independently verified
on real WebGPU hardware (Apple M4 Pro / Metal), not just device-free CI —
including several fix attempts that were tested and rejected before this one
passed.

- **Fixed:** window resize permanently blanking the canvas. Verified across 6
  consecutive resize cycles plus a post-resize orbit, 10/10 clean repaints on
  the standing hardware acceptance test.
- **Fixed:** a rare pointer-lock rejection during orbit that could surface as
  an unhandled page error; it now degrades silently and orbit continues
  without the lock.
- **Fixed:** transient white rendering artifacts under tooltips, the Add
  menu, and the Adjust Last Operation panel.
- **New:** minimal two-phase loading screen ("Downloading" / "Launching"),
  bundled local Inter subset (no external font fetch), and the loader now
  only dismisses once the 3D viewport itself has real content.
- **Improved:** critical wire is now under the 15MB LAUNCH.md budget (from
  37.8MB), and boot-to-first-paint is faster via first-boot shader cache
  seeding.

Known issues, unchanged: EEVEE viewport rendering is still not available
(Workbench only); a further staged/streaming build targeting ~15MB-to-
interactive is in progress for v0.2.

## v0.1.0-dev — 2026-08-26

First public snapshot.

- Boots the complete Blender 5.2 LTS interface in a browser tab on hardware
  WebGPU (verified on Apple Silicon / Metal)
- Workbench viewport: grid, navigation gizmo, shaded solid mode, middle-mouse
  orbit
- Edit mode: Tab, extrude (E) with live numeric readout, standard keymap
- CPython 3.13 runs the entire Python UI layer (`bl_ui`) in-tab
- OPFS-backed project storage; `.blend` save/load; OBJ / USD / glTF
  export-import
- Local-run kit: static files + a ~60-line COOP/COEP server, no install

Known issues in this build:

- Window resize blanks the canvas until the next click/mouse-move (fix already
  landed upstream; ships in v0.1.1)
- Transient white rectangles from the widget-shadow shader under
  tooltips/panels (diagnosed; fix in v0.1.1)
- EEVEE not yet available (viewport is Workbench)
- Heavy first load (~110MB compressed); staged ~15MB-to-interactive build in
  progress for v0.2
