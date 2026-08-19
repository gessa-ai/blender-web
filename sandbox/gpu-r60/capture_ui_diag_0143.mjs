// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: GPL-3.0-or-later

import { createRequire } from 'module';
import { mkdirSync, writeFileSync } from 'fs';
const require = createRequire('/Users/paws/plushly/game-platform/node_modules/');
const { chromium } = require('playwright');

const port = Number(process.argv[2] || 8148);
const outDir = '/Users/paws/blender-web/sandbox/gpu-r60/browser/ui-diagnostic';
mkdirSync(outDir, { recursive: true });
const pyexpr = [
  'import bpy, os',
  'bpy.context.preferences.view.show_splash = False',
  'def _bw_redraw():',
  '    for win in bpy.context.window_manager.windows:',
  '        if win.screen:',
  '            for area in win.screen.areas:',
  '                area.tag_redraw()',
  '    os.write(2, b"BW_R60_REDRAW\\n")',
  '    return 1.0',
  'bpy.app.timers.register(_bw_redraw, first_interval=1.0)',
].join('\n');
const url = `http://127.0.0.1:${port}/windowed.html?gate=1280x720&pyexpr=${encodeURIComponent(pyexpr)}`;
const browser = await chromium.launch({ headless: false });
const context = await browser.newContext({ viewport: { width: 1400, height: 840 }, deviceScaleFactor: 1 });
const page = await context.newPage();
const consoleLines = [];
const pageErrors = [];
page.on('console', (message) => consoleLines.push(`[${message.type()}] ${message.text()}`));
page.on('pageerror', (error) => pageErrors.push(String(error)));
await page.goto(url, { waitUntil: 'domcontentloaded' });
await page.waitForFunction(() => document.querySelector('#state')?.textContent.includes('main loop (WM_main)'),
                           { timeout: 300000 });
const canvas = page.locator('#canvas');
await canvas.hover({ position: { x: 20, y: 700 } });
await page.waitForTimeout(20000);
const state = await page.evaluate(() => {
  const c = document.querySelector('#canvas');
  const s = document.querySelector('#state');
  const r = c.getBoundingClientRect();
  return {
    state: s?.textContent || null,
    canvas: { width: c.width, height: c.height, clientWidth: c.clientWidth, clientHeight: c.clientHeight,
              rect: { x: r.x, y: r.y, width: r.width, height: r.height } },
    module: Boolean(window.__bwModule),
    crossOriginIsolated,
  };
});
await canvas.screenshot({ path: `${outDir}/workspace_1280x720.png` });
writeFileSync(`${outDir}/console.log`, `${consoleLines.join('\n')}\n`);
writeFileSync(`${outDir}/pageerrors.log`, `${pageErrors.join('\n')}\n`);
writeFileSync(`${outDir}/manifest.json`, JSON.stringify({ url, state, consoleCount: consoleLines.length,
  pageErrorCount: pageErrors.length }, null, 2));
await browser.close();
console.log(JSON.stringify({ state, consoleCount: consoleLines.length, pageErrorCount: pageErrors.length }));
