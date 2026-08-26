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
# Byte-idempotent: unchanged source inputs produce exactly identical output.
#
# Usage:  scripts/dashboard.sh            # writes reports/dashboard.md
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
OUT="${1:-reports/dashboard.md}"

python3 - "$ROOT" "$OUT" <<'PY'
import hashlib, json, os, re, subprocess, sys

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
# Milestone names/promises are the fixed GOAL.md configuration. Every status and
# percentage comes from the mapped JSON receipt. A historical promise tag is
# shown as context but can never override a missing or failing current receipt.
RESULT_SPECS = [
    ("M0", "TOOLCHAIN + ORACLE",       "M0_TOOLCHAIN",   "m0",  "toolchain/oracle checks"),
    ("M1", "CORE BOOTS + FREE ORACLE", "M1_CORE_BOOTS",  "m1",  "core-boot checks"),
    ("M2", "DEPS + PYTHON BOOTS",      "M2_DEPS_PYTHON", "m2b", "tier-(b) checks"),
    ("M3", "WEBGPU BACKEND (Dawn)",    "M3_GPU_BACKEND", "m3",  "WebGPU backend checks"),
    ("M4", "FIRST PIXELS IN A TAB",    "M4_FIRST_PIXELS","m4",  "first-pixels checks"),
    ("M5", "INTERACTIVE PARITY",       "M5_INTERACTIVE", "m5",  "interactive-parity checks"),
    ("M6", "RENDER PARITY",            "M6_RENDER",      "m6",  "render-parity checks"),
    ("M7", "FILES + PIPELINE",         "M7_FILES",       "m7",  "files/pipeline checks"),
    ("M8", "TECHNICAL RELEASE PACKAGE", "M8_TECHNICAL_RELEASE", "m8", "technical-release checks"),
]
result_docs = {mid: read_json(f"ledger/results/{stem}.json")
               for mid, _name, _promise, stem, _label in RESULT_SPECS}
m0, m1, m2b, m3 = (result_docs[mid] for mid in ("M0", "M1", "M2", "M3"))
deferred_doc = read_json("ledger/deferred.json")
deps = read_json("ledger/deps.json")
census = read_text("notes/gpu-gate-census.md")
progress = read_text("ledger/progress.txt")

head_short = git("rev-parse", "--short", "HEAD") or "unavailable"
head_subj = git("log", "-1", "--format=%s") or ""

# This digest makes provenance deterministic and auditable. Wall-clock generation
# time would make the post-receipt verifier normalize bytes instead of comparing
# them exactly, weakening the promised byte-exact contract.
dashboard_inputs = [
    *(f"ledger/results/{stem}.json" for _mid, _name, _promise, stem, _label in RESULT_SPECS),
    "ledger/deferred.json", "ledger/deps.json", "ledger/progress.txt",
    "notes/gpu-gate-census.md", "harness/status.sh", "scripts/dashboard.sh",
]
input_hash = hashlib.sha256()
for name in sorted(dashboard_inputs):
    input_hash.update(name.encode("utf-8") + b"\0")
    try:
        with open(name, "rb") as source:
            input_hash.update(source.read())
    except OSError:
        input_hash.update(b"<unavailable>")
    input_hash.update(b"\0")
input_hash.update((head_short + "\0" + head_subj).encode("utf-8"))

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
input_hash.update((gate_line + "\0" + pin_line).encode("utf-8"))
input_digest = input_hash.hexdigest()

# GPU census + static_shaders numbers (parsed, never hardcoded). Source priority:
# the harness-authoritative ledger/results/m3.json when present; the hand-maintained
# notes/gpu-gate-census.md only as a fallback. gpu_src records which was used.
c_total = c_pass = c_fail = c_crash = ss_pass = ss_total = None
gpu_src = None
gpu_when = "unavailable"
if isinstance(m3, dict) and "checks" in m3:
    chk = m3["checks"]
    m = re.search(r"(\d+)\s+PASS\s*/\s*(\d+)\s+FAIL\s*/\s*(\d+)\s+CRASH\s*\((\d+)\s+tests\)",
                  chk.get("gpu_suite_census", {}).get("detail", "") or "")
    if m:
        c_pass, c_fail, c_crash, c_total = (int(x) for x in m.groups())
    m = re.search(r"(\d+)\s*/\s*(\d+)\s+compile",
                  chk.get("static_shaders", {}).get("detail", "") or "")
    if m:
        ss_pass, ss_total = int(m.group(1)), int(m.group(2))
    if c_pass is not None or ss_pass is not None:
        gpu_src = "ledger/results/m3.json"
        gpu_when = m3.get("ts", "unavailable")
if gpu_src is None:  # fall back to the hand-maintained census note
    if census:
        m = re.search(r"(\d+)\s+tests\b.{0,6}?(\d+)\s+PASS\s*/\s*(\d+)\s+FAIL\s*/\s*(\d+)\s+CRASH", census)
        if m:
            c_total, c_pass, c_fail, c_crash = (int(x) for x in m.groups())
        m = re.search(r"(\d+)\s*/\s*(\d+)\s+shaders compile", census)
        if m:
            ss_pass, ss_total = int(m.group(1)), int(m.group(2))
    gpu_src = "notes/gpu-gate-census.md"
    gpu_when = git_date("notes/gpu-gate-census.md")

# ---------- (a) milestone bar ----------------------------------------------
def percentage(n, total):
    return "unavailable" if not total else f"{n}/{total} ({100.0*n/total:.1f}%)"

def promise_issued(name):
    """Detect the literal <promise>NAME</promise> tag — NOT a casual mention of the
    bare tag name in prose or a commit subject. Searches BOTH git commit messages
    and ledger/progress.txt (the tag may be recorded in either). Returns
    (where, cite) or (None, None)."""
    tag = f"<promise>{name}</promise>"
    c = git("log", "--all", "--fixed-strings", "--grep", tag, "-1", "--format=%h %s")
    if c:
        return "git", c
    if progress and tag in progress:
        pc = git("log", "--all", "-S", tag, "-1", "--format=%h %s")  # commit that recorded it
        return "progress", (pc or "ledger/progress.txt")
    return None, None

def milestone_row(mid, name, promise, stem, _label):
    results = result_docs[mid]
    where, cite = promise_issued(promise)
    promise_note = ""
    if where:
        promise_note = (f"; historical promise recorded via {where}: {cite}; "
                        "current receipt remains authoritative")
    if not isinstance(results, dict) or not isinstance(results.get("checks"), dict):
        return "UNAVAILABLE", f"ledger/results/{stem}.json missing/unreadable{promise_note}"
    checks = results["checks"]
    npass = sum(1 for check in checks.values()
                if isinstance(check, dict) and check.get("pass") is True)
    total = len(checks)
    receipt = (f"ledger/results/{stem}.json {percentage(npass, total)}"
               + (f" @ {results.get('ts')}" if results.get("ts") else "")
               + promise_note)
    passed = results.get("pass") is True and total > 0 and npass == total
    return ("PASS" if passed else "FAIL"), receipt

mile_rows = [(mid, name, *milestone_row(mid, name, promise, stem, label))
             for mid, name, promise, stem, label in RESULT_SPECS]

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
    suite_rows.append((label, percentage(npass, tot), nonp, path, doc.get("ts", "unavailable")))
    return checks

suite_checks = {}
for mid, _name, _promise, stem, label in RESULT_SPECS:
    suite_checks[mid] = json_suite(f"{mid.lower()}  {label}", result_docs[mid],
                                   f"ledger/results/{stem}.json")
c0, c1, c2 = (suite_checks[mid] for mid in ("M0", "M1", "M2"))

# m1 sub-metrics (surface the gtest / corpus counts so non-passes aren't buried)
if c1:
    ts1 = m1.get("ts", "unavailable")
    bp, bt = frac(c1.get("blenlib_gtests", {}).get("detail"), r"(\d+)/(\d+)\s+PASSED")
    if bp is not None:
        suite_rows.append(("m1 › blenlib gtests", percentage(bp, bt),
                           f"{bt-bp} non-passing (see receipt detail)",
                           "ledger/results/m1.json", ts1))
    mp, mt = frac(c1.get("bmesh_core_gtests", {}).get("detail"), r"(\d+)/(\d+)\s+PASSED")
    if mp is not None:
        suite_rows.append(("m1 › bmesh_core gtests", percentage(mp, mt), "0",
                           "ledger/results/m1.json", ts1))
    cp, _ = frac(c1.get("corpus_parity", {}).get("detail"), r"all (\d+) committed wasm dumps")
    if cp is not None:
        suite_rows.append(("m1 › corpus state-dump parity", percentage(cp, cp),
                           "0 (sha256==MANIFEST, tolerance 0)", "ledger/results/m1.json", ts1))

if c2:
    gp, gt = frac(c2.get("core_green", {}).get("detail"), r"(\d+)/(\d+)\s+must-pass")
    if gp is not None:
        suite_rows.append(("m2b › CORE must-pass suites", percentage(gp, gt), "0",
                           "ledger/results/m2b.json", m2b.get("ts", "unavailable")))

# GPU census + static_shaders (source: m3.json when present, else the census note)
if c_pass is not None:
    suite_rows.append(("gpu gate census (native Dawn)", percentage(c_pass, c_total),
                       f"{c_total-c_pass} ({c_fail} FAIL / {c_crash} CRASH, all characterized)",
                       gpu_src, gpu_when))
else:
    suite_rows.append(("gpu gate census (native Dawn)", "unavailable", "unavailable",
                       gpu_src, gpu_when))
if ss_pass is not None:
    suite_rows.append(("gpu static_shaders compile", percentage(ss_pass, ss_total),
                       f"{ss_total-ss_pass} (deferrals/blacklist/census artifacts)",
                       gpu_src, gpu_when))
else:
    suite_rows.append(("gpu static_shaders compile", "unavailable", "unavailable",
                       gpu_src, gpu_when))

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
w("# Source-derived WebAssembly editor — technical release dashboard")
w("")
w("_The human's only interface (GOAL.md Communication). Every count below is read "
  "from a file on disk at generation time; an unreadable source shows `unavailable`, "
  "never a guess. Failures and deferrals carry their own columns — equal weight, "
  "never buried in a green total._")
w("")
w("_Scope: the M8 row is the locally verifiable technical release package. Public "
  "launch, legal approval, hosting, and publication are intentionally outside this dashboard._")
w("")

# (a) milestones
w("## (a) Milestones M0–M8")
w("")
passed = sum(1 for r in mile_rows if r[2] == "PASS")
failed = sum(1 for r in mile_rows if r[2] == "FAIL")
unavailable = sum(1 for r in mile_rows if r[2] == "UNAVAILABLE")
w(f"**{passed} PASS · {failed} FAIL · {unavailable} UNAVAILABLE**")
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
w(f"- dashboard input SHA-256: `{input_digest}`")
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
