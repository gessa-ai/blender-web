// SPDX-License-Identifier: GPL-3.0-or-later
// Offline proof for the demo: boot a session and record EVERY network request the
// tab makes. Blender-web is fully local (COOP/COEP, all assets from /bin + /py on
// localhost); a faithful "network tab" shows zero external hosts. Fails if any
// request targets a non-localhost origin.
import { createRequire } from 'module';
import { writeFileSync } from 'fs';
const require = createRequire('/Users/paws/plushly/game-platform/node_modules/');
const { chromium } = require('playwright');
const PORT = parseInt(process.argv[2] || '8125', 10);
const SESSION = process.argv[3] || 'm5_core.object_select_all';
const OUT = '/Users/paws/blender-web/sandbox/m5-prep/wasm-out';

const browser = await chromium.launch({ headless: false });
const page = await (await browser.newContext({ viewport: { width: 1380, height: 820 }, deviceScaleFactor: 1 })).newPage();
const reqs = [];
page.on('request', (r) => { try { reqs.push(new URL(r.url()).host || r.url().slice(0, 40)); } catch (_) { reqs.push(r.url().slice(0, 40)); } });

const url = `http://localhost:${PORT}/?session=${encodeURIComponent(SESSION)}`;
console.log('offline-proof boot', url);
await page.goto(url, { waitUntil: 'domcontentloaded' });
await page.waitForFunction(() => {
  const s = document.querySelector('#state');
  return s && s.textContent.includes('main loop (WM_main)');
}, null, { timeout: 240000 });
await page.waitForTimeout(20000); // let the session run + any late fetch fire

const hosts = [...new Set(reqs)].sort();
const external = hosts.filter((h) => !/^localhost(:\d+)?$/.test(h) && !/^127\.0\.0\.1(:\d+)?$/.test(h));
const summary = {
  session: SESSION, total_requests: reqs.length, unique_hosts: hosts,
  external_hosts: external, offline_ok: external.length === 0,
};
writeFileSync(`${OUT}/offline-proof.json`, JSON.stringify(summary, null, 1) + '\n');
console.log('unique hosts:', JSON.stringify(hosts));
console.log('external hosts:', JSON.stringify(external));
console.log(external.length === 0 ? 'OFFLINE_OK (no external hosts)' : 'OFFLINE_FAIL');
await browser.close();
