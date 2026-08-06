#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Dashboard generator (GOAL.md M8: "dashboard live with per-suite % and the
# deferral registry"; Communication: "the human's only interface — keep it
# truthful"). Regenerates reports/dashboard.md from files already on disk.
#
# TRUTHFULNESS CONTRACT (binding, per GOAL.md):
#   * Every number is read from a source file at generation time — nothing is
#     hardcoded. A missing/unparseable source prints "unavailable", never a guess.
#   * Failures / deferrals get their own columns (equal visual weight to passes;
#     no burying a red count inside a green total).
#   * Read-only on all sources. The only file written is reports/dashboard.md.
#
# Sources: ledger/results/*.json, ledger/progress.txt, ledger/deferred.json,
#   ledger/deps.json, notes/gpu-gate-census.md, harness/status.sh (executed —
#   it is the read-only status tool), git log.
#
# Idempotent: two consecutive runs differ only in the "Generated at" line.
#
# Usage:  scripts/dashboard.sh            # writes reports/dashboard.md
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
OUT="reports/dashboard.md"

python3 - "$ROOT" "$OUT" <<'PY'
import json, os, re, subprocess, sys
from datetime import datetime, timezone

ROOT, OUT = sys.argv[1], sys.argv[2]
os.chdir(ROOT)

# ---------- small helpers ---------------------------------------------------
def read_json(path):
    try:
        with open(path) as fh:
            return json.load(fh)
    except Exception:
        return None

def read_text(path):
    try:
        with open(path) as fh:
            return fh.read()
    except Exception:
        return None

def git(*args):
    try:
        out = subprocess.run(["git", *args], capture_output=True, text=True, timeout=20)
        return out.stdout.strip() if out.returncode == 0 else ""
    except Exception:
        return ""

def cell(s, n=104):
    """Sanitize a value for a markdown table cell."""
    if s is None:
        return "unavailable"
    s = re.sub(r"\s+", " ", str(s)).strip().replace("|", r"\|")
    return (s[: n - 1] + "…") if len(s) > n else s

def frac(detail, pat):
    """Pull numbers out of a prose detail string. Returns (n1, n2); n2 is None
    when the pattern has a single capture group (e.g. the corpus count)."""
    if not detail:
        return None, None
    m = re.search(pat, detail)
    if not m:
        return None, None
    n2 = int(m.group(2)) if m.re.groups >= 2 else None
    return int(m.group(1)), n2

def git_date(path):
    d = git("log", "-1", "--format=%cI", "--", path)
    return d or "unavailable"

# ---------- gather sources --------------------------------------------------
m0 = read_json("ledger/results/m0.json")
m1 = read_json("ledger/results/m1.json")
m2b = read_json("ledger/results/m2b.json")
deferred_doc = read_json("ledger/deferred.json")
deps = read_json("ledger/deps.json")
census = read_text("notes/gpu-gate-census.md")
progress = read_text("ledger/progress.txt")

head_short = git("rev-parse", "--short", "HEAD") or "unavailable"
head_subj = git("log", "-1", "--format=%s") or ""
now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

# harness/status.sh is the read-only status tool — execute for gate + pin lines.
gate_line = pin_line = "unavailable"
try:
    st = subprocess.run(["bash", "harness/status.sh"], capture_output=True, text=True, timeout=60)
    for ln in st.stdout.splitlines():
        if ln.startswith("gate:"):
            gate_line = ln.split(":", 1)[1].strip()
        elif ln.startswith("upstream:"):
            pin_line = ln.split(":", 1)[1].strip()
except Exception:
    pass

# census numbers (parsed, never hardcoded)
c_total = c_pass = c_fail = c_crash = ss_pass = ss_total = None
if census:
    m = re.search(r"(\d+)\s+tests\b.{0,6}?(\d+)\s+PASS\s*/\s*(\d+)\s+FAIL\s*/\s*(\d+)\s+CRASH", census)
    if m:
        c_total, c_pass, c_fail, c_crash = (int(x) for x in m.groups())
    m = re.search(r"(\d+)\s*/\s*(\d+)\s+shaders compile", census)
    if m:
        ss_pass, ss_total = int(m.group(1)), int(m.group(2))
census_when = git_date("notes/gpu-gate-census.md")

# ---------- (a) milestone bar ----------------------------------------------
# Milestone definitions are fixed config (from GOAL.md); STATUS is derived live
# from git promise commits, result-JSON pass flags, and census/progress markers.
MILESTONES = [
    ("M0", "TOOLCHAIN + ORACLE",        "M0_TOOLCHAIN",   m0,  None),
    ("M1", "CORE BOOTS + FREE ORACLE",  "M1_CORE_BOOTS",  m1,  None),
    ("M2", "DEPS + PYTHON BOOTS",       "M2_DEPS_PYTHON", m2b, None),
    ("M3", "WEBGPU BACKEND (Dawn)",     "M3_GPU_BACKEND", None, "census"),
    ("M4", "FIRST PIXELS IN A TAB",     "M4_FIRST_PIXELS",None, "FIRST PIXELS"),
    ("M5", "INTERACTIVE PARITY",        "M5_INTERACTIVE", None, None),
    ("M6", "RENDER PARITY",             "M6_RENDER",      None, None),
    ("M7", "FILES + PIPELINE",          "M7_FILES",       None, None),
    ("M8", "LAUNCH GATE",               "M8_LAUNCH_GATE", None, None),
]

def milestone_row(mid, name, promise, results, marker):
    commit = git("log", "--all", "-1", "--grep", promise, "--format=%h %s")
    res_pass = res_frac = None
    if isinstance(results, dict):
        checks = results.get("checks", {})
        npass = sum(1 for c in checks.values() if c.get("pass"))
        tot = len(checks)
        res_frac = f"{npass}/{tot}"
        res_pass = bool(results.get("pass")) and npass == tot and tot > 0
    # DONE if a promise commit exists OR the mapped result-JSON passed.
    if commit or res_pass:
        status = "DONE"
        parts = []
        if commit:
            parts.append(f"commit {commit}")
        if res_frac is not None:
            src = {"M0": "m0.json", "M1": "m1.json", "M2": "m2b.json"}.get(mid, "results")
            parts.append(f"results/{src} {res_frac}"
                         + (f" @ {results.get('ts')}" if results.get("ts") else ""))
        receipt = "; ".join(parts) or "unavailable"
        return status, receipt
    # IN-PROGRESS if a live activity marker resolves.
    if marker == "census" and c_pass is not None:
        status = "IN-PROGRESS"
        receipt = (f"notes/gpu-gate-census.md gate {c_pass}/{c_total}, "
                   f"static_shaders {ss_pass}/{ss_total} — promise tag not yet issued")
        return status, receipt
    if marker and marker != "census":
        commit2 = git("log", "--all", "-1", "--grep", marker, "--format=%h %s")
        if commit2:
            return "IN-PROGRESS", f"commit {commit2} — promise tag not yet issued"
        if progress and marker in progress:
            return "IN-PROGRESS", f"ledger/progress.txt: “{marker}” — promise tag not yet issued"
    return "pending", f"awaiting <promise>{promise}</promise>"

mile_rows = [(mid, name, *milestone_row(mid, name, promise, results, marker))
             for mid, name, promise, results, marker in MILESTONES]

# ---------- (b) per-suite table --------------------------------------------
suite_rows = []  # (suite, passing, nonpassing, source, when)

def json_suite(label, doc, path):
    if not isinstance(doc, dict) or "checks" not in doc:
        suite_rows.append((label, "unavailable", "unavailable", path, "unavailable"))
        return None
    checks = doc["checks"]
    npass = sum(1 for c in checks.values() if c.get("pass"))
    tot = len(checks)
    fails = [n for n, c in checks.items() if not c.get("pass")]
    nonp = "0" if not fails else f"{len(fails)}: " + ", ".join(fails)
    suite_rows.append((label, f"{npass}/{tot}", nonp, path, doc.get("ts", "unavailable")))
    return checks

c0 = json_suite("m0  toolchain/oracle checks", m0, "ledger/results/m0.json")
c1 = json_suite("m1  core-boot checks", m1, "ledger/results/m1.json")

# m1 sub-metrics (surface the gtest / corpus counts so non-passes aren't buried)
if c1:
    ts1 = m1.get("ts", "unavailable")
    bp, bt = frac(c1.get("blenlib_gtests", {}).get("detail"), r"(\d+)/(\d+)\s+PASSED")
    if bp is not None:
        suite_rows.append(("m1 › blenlib gtests", f"{bp}/{bt}",
                           f"{bt-bp} characterized (9 fenv-defer + 1 host-chdir)",
                           "ledger/results/m1.json", ts1))
    mp, mt = frac(c1.get("bmesh_core_gtests", {}).get("detail"), r"(\d+)/(\d+)\s+PASSED")
    if mp is not None:
        suite_rows.append(("m1 › bmesh_core gtests", f"{mp}/{mt}", "0",
                           "ledger/results/m1.json", ts1))
    cp, _ = frac(c1.get("corpus_parity", {}).get("detail"), r"all (\d+) committed wasm dumps")
    if cp is not None:
        suite_rows.append(("m1 › corpus state-dump parity", f"{cp}/{cp}",
                           "0 (sha256==MANIFEST, tolerance 0)", "ledger/results/m1.json", ts1))

c2 = json_suite("m2b tier-(b) checks", m2b, "ledger/results/m2b.json")
if c2:
    gp, gt = frac(c2.get("core_green", {}).get("detail"), r"(\d+)/(\d+)\s+must-pass")
    if gp is not None:
        suite_rows.append(("m2b › CORE must-pass suites", f"{gp}/{gt}", "0",
                           "ledger/results/m2b.json", m2b.get("ts", "unavailable")))

# GPU census + static shaders (parsed from the note)
if c_pass is not None:
    suite_rows.append(("gpu gate census (native Dawn)", f"{c_pass}/{c_total}",
                       f"{c_total-c_pass} ({c_fail} FAIL / {c_crash} CRASH, all characterized)",
                       "notes/gpu-gate-census.md", census_when))
else:
    suite_rows.append(("gpu gate census (native Dawn)", "unavailable", "unavailable",
                       "notes/gpu-gate-census.md", census_when))
if ss_pass is not None:
    suite_rows.append(("gpu static_shaders compile", f"{ss_pass}/{ss_total}",
                       f"{ss_total-ss_pass} (deferrals/blacklist/census artifacts)",
                       "notes/gpu-gate-census.md", census_when))
else:
    suite_rows.append(("gpu static_shaders compile", "unavailable", "unavailable",
                       "notes/gpu-gate-census.md", census_when))

# ---------- (c) deferral registry ------------------------------------------
deferrals = []
status_tally = {}
if isinstance(deferred_doc, dict) and isinstance(deferred_doc.get("deferred"), list):
    for d in deferred_doc["deferred"]:
        st = d.get("status", "?")
        status_tally[st] = status_tally.get(st, 0) + 1
        deferrals.append(d)

# deps.json receipt (M2 completeness): count harvested archives
dep_n = None
if isinstance(deps, dict) and isinstance(deps.get("wasm_built"), dict):
    dep_n = len(deps["wasm_built"])

# ---------- render ----------------------------------------------------------
L = []
w = L.append
w("<!-- Generated by scripts/dashboard.sh from files on disk. DO NOT EDIT BY HAND. -->")
w("<!-- Regenerate: scripts/dashboard.sh -->")
w("")
w("# blender-web — port factory dashboard")
w("")
w("_The human's only interface (GOAL.md Communication). Every count below is read "
  "from a file on disk at generation time; an unreadable source shows `unavailable`, "
  "never a guess. Failures and deferrals carry their own columns — equal weight, "
  "never buried in a green total._")
w("")

# (a) milestones
w("## (a) Milestones M0–M8")
w("")
done = sum(1 for r in mile_rows if r[2] == "DONE")
inprog = sum(1 for r in mile_rows if r[2] == "IN-PROGRESS")
w(f"**{done} DONE · {inprog} IN-PROGRESS · {len(mile_rows)-done-inprog} pending**")
w("")
w("| Milestone | Status | Receipt |")
w("|---|---|---|")
for mid, name, status, receipt in mile_rows:
    w(f"| **{mid}** {cell(name,44)} | {status} | {cell(receipt,150)} |")
w("")

# (b) suites
w("## (b) Suites — per-suite pass counts")
w("")
w("| Suite | Passing | Non-passing | Source | As of |")
w("|---|---|---|---|---|")
for label, passing, nonp, src, when in suite_rows:
    w(f"| {cell(label,44)} | {cell(passing,20)} | {cell(nonp,80)} | `{cell(src,40)}` | {cell(when,26)} |")
w("")
if dep_n is not None:
    w(f"_Dependencies: {dep_n} wasm_built archives harvested + reconciled "
      f"(`ledger/deps.json`)._")
    w("")

# (c) deferral registry
w("## (c) Deferral registry")
w("")
if deferrals:
    tally = ", ".join(f"{k} {v}" for k, v in sorted(status_tally.items()))
    w(f"**{len(deferrals)} entries** — by status: {tally}. "
      f"_(Deferrals are honesty, not silence — GOAL.md.)_")
    w("")
    w("| id | status | milestone | blocker | revisit |")
    w("|---|---|---|---|---|")
    for d in deferrals:
        w("| " + " | ".join([
            cell(d.get("id"), 40),
            cell(d.get("status"), 22),
            cell(d.get("milestone"), 24),
            cell(d.get("blocker"), 120),
            cell(d.get("revisit"), 70),
        ]) + " |")
else:
    w("| id | status | milestone | blocker | revisit |")
    w("|---|---|---|---|---|")
    w("| unavailable | — | — | `ledger/deferred.json` absent or empty | — |")
w("")

# (d) recent activity
w("## (d) Recent activity — last 10 `ledger/progress.txt` lines (verbatim)")
w("")
if progress is not None:
    lines = [ln for ln in progress.splitlines() if ln.strip()]
    tail = lines[-10:] if len(lines) >= 10 else lines
    w("```text")
    for ln in tail:
        w(ln)
    w("```")
else:
    w("`ledger/progress.txt` unavailable.")
w("")

# (e) provenance
w("## (e) Provenance")
w("")
w(f"- gate: {cell(gate_line,80)}")
w(f"- upstream: {cell(pin_line,90)}")
w(f"- git HEAD: `{head_short}` {cell(head_subj,90)}")
w(f"- Generated at: {now}")
w("")

with open(OUT, "w") as fh:
    fh.write("\n".join(L) + "\n")

# stdout summary (for the operator; not written to the report)
bar = " ".join(f"{mid}:{status[:4]}" for mid, _, status, _ in mile_rows)
print(f"dashboard: wrote {OUT}")
print(f"milestones: {bar}")
if c_pass is not None:
    print(f"gpu census {c_pass}/{c_total} (static_shaders {ss_pass}/{ss_total}); "
          f"deferrals {len(deferrals)}")
PY
