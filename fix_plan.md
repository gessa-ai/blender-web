# fix_plan.md — current milestone: M0 TOOLCHAIN + ORACLE
> BLOCKER (human): re-auth the claude CLI for headless use — run `claude setup-token` (or an interactive /login). Until then only codex workers can execute; the driver loop is claude-based and will not start.
- [ ] M0.1 DONE 2026-08-03: upstream at pin fbe6228777e7 (tip of blender-v5.2-release), LFS assets deferred as pointers (lfs.url set to projects.blender.org for later `git lfs pull --include assets/`).
- [ ] M0.2 Install pinned emsdk under tools/emsdk (>=4.0.10; record exact version in oracle/TOOLCHAIN); compile+run a hello-world wasm in node AND a browser smoke page.
- [ ] M0.3 Oracle online: pinned native Blender 5.2.0 headless on this host (macOS arm64 official archive under oracle/, or Docker linux image); oracle/bpy.sh runs `blender -b --python-expr`; verify version string == 5.2.0; install oiiotool (brew openimageio) for image diffs.
- [ ] M0.4 harness/buildwrap.sh proven: wraps an emcc build, one-line success, first-50-errors failure summary, full log under ledger/buildlogs/.
- [ ] M0.5 harness/run.sh v1 + status.sh: --scope m0 runs toolchain+oracle smokes and writes ledger/results/*.json; then `touch .claude/harness.lock` to activate write-protection on harness/.
- [ ] M0.6 Draft build_files config: patches/blender_web.cmake per GOAL standing decisions (derive from blender_lite + blender_headless option sets; document every forced-OFF in ledger/deps.json).
- [ ] M0.7 Compliance skeleton: LICENSES/ (GPL-2.0-or-later, GPL-3.0-or-later), NOTICE, PROVENANCE.md, REUSE.toml, THIRD-PARTY.md; run `reuse lint` locally (pipx install reuse) until green.
- [ ] M0.8 Ops: disk audit (need >=40GB free before M2 — currently ~19GB: identify reclaim or external volume; PAGE if unresolvable); write notes/codex-cli.md from `codex exec --help` (verify non-interactive + model flags for worker use).
- [ ] M0.9 (deferred until GitHub repo exists) CI skeleton — local-first for now; revisit at M1 exit.
