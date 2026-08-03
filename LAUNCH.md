# LAUNCH.md — compliance, naming, and the X post

The launch is gated on M8 plus every box here. Compliance is the easy part; framing is the risk. Context that must inform the post: on 2026-05-01 the Blender Foundation publicly apologized for accepting Anthropic as a Development Fund patron after community backlash, converted it to a one-time donation, and stated "Blender is made by humans for humans. No generative AI functionality is currently available or planned." Blender's contributor handbook now bans AI commit authorship and treats unreviewed AI code as a copyright risk. This project is legally clean and openly derivative — but the framing must not re-detonate that fight.

## Repo/product identity

- [ ] Product name is its own brand; "Blender" never leads the name, repo, domain, or handle; no Blender logo anywhere (app, favicon, social, store art). Permitted phrasing (their policy's descriptive/nominative allowance): "source-derived from Blender," "built from Blender's open-source (GPL) code," "compatible with Blender files."
- [ ] Standing disclaimer in README, site footer, and repo description: "Not affiliated with, endorsed by, or sponsored by the Blender Foundation. Blender® is a registered trademark of the Blender Foundation."

## License & attribution (day-one state, enforced by CI)

- [ ] Aggregate license GPL-3.0-or-later; derived files individually GPL-2.0-or-later (or their true upstream license, e.g. Apache-2.0 for Cycles-derived); full texts in `LICENSES/`.
- [ ] Every derived file: upstream `SPDX-FileCopyrightText` preserved verbatim + ours added + SPDX identifier + one provenance line citing the upstream path and pinned commit. `PROVENANCE.md` maps modules → upstream paths → pin.
- [ ] `NOTICE`/`AUTHORS` credits Blender Authors and the Blender Foundation as origin. `THIRD-PARTY.md` lists every dep + license; all GPL-compatible.
- [ ] `reuse lint` green. App footer links "Source code (GPL)" to the repo (GPLv3 §6(d) — the repo is the preferred-form source, not minified bundles).
- [ ] Git history: human author config; AI assistance disclosed via `Assisted-by:` trailers; no AI `Co-authored-by`.
- [ ] If any Blender-derived code ever runs server-side without being shipped to the client, license that portion AGPL-3.0-or-later. (Pure client-side ⇒ GPL suffices.)
- [ ] A GPL-literate lawyer has skimmed the repo license posture and the final post wording before launch.

## The 30-second bar (demo packaging spec — M8 gates on this)

Engineered from the launches that worked (Web HL2, Doom 3 wasm, Photopea, v86, Photoshop web):

- [ ] **Staged load:** small first payload reaching an **interactive viewport with the default cube in ≤5–8 s** on a mid laptop; the rest streams asynchronously into cache (the Doom 3 pattern: ~15 MB to interactive, hundreds of MB streamed after). Real progress UI with phase labels and MB counters — never a bare spinner. Service-worker precache so the skeptic's reload is near-instant (Photoshop's documented 75% init cut).
- [ ] **First interaction proves it's local:** zero-latency middle-mouse orbit, then Tab → edit mode → extrude. Frame-instant response is the proof.
- [ ] **Proof-of-native, explicit and testable** — this is the differentiation axis, because the only incumbent "Blender in your browser" (Vagon) is pixel-streaming: a visible line "Runs entirely on your device — WebAssembly + WebGPU. No server, no streaming," an invited *disconnect-your-network* test, a network tab that goes quiet after load, the `.wasm` visible in Sources.
- [ ] **Wow moment within 30 s:** orbit the preloaded **Classroom scene (CC0 — zero attribution friction; benchmark scenes also CC0; CC-BY splash files only with visible credit)**, or the killshot — **drag-drop the viewer's own `.blend` and orbit their scene** (the Photopea/v86 "it opened my file" moment).
- [ ] **Fidelity tells within reach in 10 s:** exact splash (version art, New File/Recent, version bottom-right), default cube + camera + light on the standard grey world, correct theme and fonts, and the keymap — Tab, G/R/S with X/Y/Z constraints, MMB orbit, Shift+A, N/T panels, numpad views, deep Ctrl+Z. One wrong shortcut reads as "three.js toy."
- [ ] **Shareable state:** `?scene=classroom`-style URLs so the artifact self-propagates in threads.
- [ ] **Ops:** static host + CDN sized for the hug-of-death; desktop-first framing with mobile limitations stated up front (every port thread tests mobile and finds it wanting — pre-empt it).
- [ ] **Post mechanics:** lead post = one-line claim + a <30 s native-capture MP4 (click → splash → orbit → Tab/extrude → drag-drop a .blend) + the live link; numbered reply thread: how-it's-not-streaming (network-tab screenshot + wifi-kill challenge) → why-this-was-considered-impossible (Blender devs' own GL-4.3/Python/linker walls — borrowed difficulty amplifies the feat) → GPL/tech deep-dive + repo → try-it URLs. Simultaneous Show HN with the author's first comment listing every limitation; be present for the first two hours. Tue–Thu US morning.

## Proof artifacts the post links to

- [ ] Live demo (Cloudflare Pages, COOP/COEP) surviving the skeptic's path: open → Tab into edit mode → model → modifier → material → animate → render preview → save/export — no dead ends.
- [ ] Live conformance dashboard: per-suite pass %, versus pinned Blender 5.2.0, plus the deferral registry with named blockers (Cycles-final: no WebGPU hardware ray tracing/bindless yet; OSL: no JIT in the sandbox; Mantaflow: no port; >16 GB scenes: Memory64 ceiling). Publishing the deferrals is what makes the claim unfalsifiable-proof.
- [ ] A methodology writeup (how the fleet worked: the WebGPU backend, GHOST-web, the harness) — this is where the AI story lives, fully and proudly, with receipts.

## The post

**Lead with the artifact, not the tool.** Recommended shape:

> "<PORT_NAME>: Blender's full editor, running natively in your browser — no streaming, no install. Faithfully source-derived from Blender (GPL, every file attributed, source one click away). Live demo + parity dashboard: <links>"

Then, in-thread or in the writeup, the honest methodology: built by orchestrated Claude agents that wrote the WebGPU backend, the web platform layer, and the port harness, with every change verified against native Blender and human-reviewed — `Assisted-by` trailers throughout.

**Don't:** lead with "AI agents rewrote Blender" (aimed at the one community currently most raw about exactly this, twelve weeks after the Anthropic apology); use "Blender for the Web"-style headline naming or the mark in a tagline; imply endorsement; claim clean-room or hint at any relicensing; post before the demo survives the skeptic's path. The AI-builder audience will surface the methodology on its own — that's the second wave, and it costs nothing to let them do it.

**Community etiquette:** announce on devtalk/Blender Artists with a respectful "what this is / what it isn't" post crediting Blender Authors; state upstream-friendliness (patches offered where wanted); expect and absorb skepticism with the dashboard, not with arguing.
