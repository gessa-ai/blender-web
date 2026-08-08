// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: GPL-3.0-or-later
//
// boot_regchain.mjs - decisive characterization of the addon-registration chain the
// m8-staged-deploy note blamed on "inspect->dis / dis.py absent". Exercises, inside
// the WM-worker, the exact chain (dataclasses->inspect->dis), imports the named addon
// modules (bl_pkg, pose_library), and the urllib3/requests transport chain, reporting
// each exception verbatim. Proves dis is NOT the culprit and identifies the real one.
import { createRequire } from 'module';
const require = createRequire('/Users/paws/plushly/game-platform/node_modules/');
const { chromium } = require('playwright');
const fs = require('fs');
const PORT = parseInt(process.argv[2] || '8130', 10);
const BASE = `http://localhost:${PORT}`;
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const PY = [
  'import bpy,sys,importlib',
  'def _b():',
  '    r=[]',
  "    for c in ['dataclasses','inspect','dis','opcode','_opcode']:",
  '        try: importlib.import_module(c); r.append("CHAIN_OK "+c)',
  '        except Exception as e: r.append("CHAIN_FAIL "+c+" "+repr(e)[:120])',
  "    for m in ['bl_pkg','pose_library','_bpy_internal']:",
  '        try: importlib.import_module(m); r.append("ADDON_IMPORT_OK "+m)',
  '        except Exception as e: r.append("ADDON_IMPORT_FAIL "+m+" "+repr(e)[:140])',
  "    for m in ['requests','urllib3']:",
  '        try: importlib.import_module(m); r.append("NET_OK "+m)',
  '        except Exception as e: r.append("NET_FAIL "+m+" "+repr(e)[:140])',
  '    try:',
  '        import addon_utils',
  '        en=[a.module for a in bpy.context.preferences.addons]',
  '        r.append("ENABLED_ADDONS "+str(sorted(en))[:400])',
  '    except Exception as e: r.append("ADDON_ENUM_FAIL "+repr(e)[:120])',
  '    f=open("/bw/_battery2","w"); f.write(chr(10).join(r)); f.close(); return None',
  'bpy.app.timers.register(_b, first_interval=0.6)',
].join('\n');

const url = `${BASE}/index.html?gate=1280x720&pyexpr=${encodeURIComponent(PY)}`;
const browser = await chromium.launch({ headless: false });
const ctx = await browser.newContext({ viewport: { width: 1400, height: 900 }, deviceScaleFactor: 1 });
const page = await ctx.newPage();
const lines = [];
page.on('console', (m) => lines.push(m.text()));
page.on('pageerror', (e) => lines.push('PAGEERR ' + (e.message || e)));
await page.goto(url, { waitUntil: 'domcontentloaded' });
try { await page.waitForFunction(() => { const s = document.querySelector('#state'); return s && s.textContent.includes('main loop (WM_main)'); }, null, { timeout: 180000 }); } catch (e) { console.log('WM_main FAIL ' + e.message); }
const readFile = (p) => page.evaluate((x) => { try { return window.__bwModule.FS.readFile(x, { encoding: 'utf8' }); } catch (e) { return null; } }, p);
let b = null;
for (let i = 0; i < 60; i++) { b = await readFile('/bw/_battery2'); if (b) break; await sleep(500); }
console.log('REGCHAIN RESULT:\n' + (b || '(none)'));
const susp = lines.filter((l) => /Traceback|ImportError|ModuleNotFoundError|No module named|dis/i.test(l));
console.log('boot-console suspect lines (' + susp.length + '):');
susp.slice(0, 30).forEach((l) => console.log('  >> ' + l.slice(0, 160)));
fs.writeFileSync('/Users/paws/blender-web/sandbox/m8-python-trim/artifacts/console_regchain.log', lines.join('\n'));
await ctx.close(); await browser.close();
process.exit(0);
