// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: GPL-3.0-or-later
//
// r53 (L-A backend primitive) - PRIMITIVE PROOF for the production kick/latch/settle
// readback contract (notes/m5-sync-readback-contract-design.md, wgpu_readback.{cc,hh}).
//
// Drives a REAL readback through the production seam (GPU_framebuffer_read_color ->
// WGPUFrameBuffer::read -> WGPUTexture::read) on a PERSISTENT GPUOffScreen whose colour
// texture is stable across reads, so the "return the latched bytes when settled" contract
// (kick-now, fill-one-tick-late) is exercised end to end:
//   read0 : first read of the texture -> KICK (miss) -> conservative interim (zeros)
//   read1 : after ticks let AllowSpontaneous fire -> LATCH -> fill-late HIT -> true bytes
//   read2 : steady-state confirm -> true bytes
// The offscreen is cleared to a KNOWN colour (0.2,0.6,0.9,1.0) so "matches on-screen
// content" is a known-answer check. Baseline (r49) measured constant 0/255 on this seam.
//
// Usage: NODE_PATH=/Users/paws/plushly/game-platform/node_modules \
//   node sandbox/gpu-r53-readback/probe_readback_fill_late.mjs [port]

import { createRequire } from 'module';
import { writeFileSync } from 'fs';
const require = createRequire('/Users/paws/plushly/game-platform/node_modules/');
const { chromium } = require('playwright');

const PORT = parseInt(process.argv[2] || '8136', 10);
const GW = 1280, GH = 720;
const BASE = `http://localhost:${PORT}`;
const OUT = '/Users/paws/blender-web/sandbox/gpu-r53-readback/evidence';
const BOOT_MS = 240000;
const SETTLE_MS = 120000;

const PY = [
  'import bpy, gpu, os',
  'bpy.context.preferences.view.show_splash = False',
  'W = 64; H = 64',
  'COL = (0.2, 0.6, 0.9, 1.0)',
  '_off = None',
  '_st = {"n": 0, "phase": 0}',
  'def _flat(x, out):',
  '    if isinstance(x, (list, tuple)):',
  '        for e in x: _flat(e, out)',
  '    else:',
  '        out.append(int(x))',
  'def _do_read(tag):',
  '    global _off',
  '    try:',
  '        with _off.bind():',
  '            fb = gpu.state.active_framebuffer_get()',
  '            fb.clear(color=COL)',
  '            buf = fb.read_color(0, 0, W, H, 4, 0, "UBYTE")',
  '        flat = []',
  '        _flat(buf.to_list(), flat)',
  '        n = len(flat)',
  '        mx = max(flat) if n else 0',
  '        nz = sum(1 for v in flat if v > 0)',
  '        sample = flat[:8]',
  '        try:',
  '            with open("/tmp/r53_%s.bin" % tag, "wb") as f:',
  '                f.write(bytes(flat))',
  '        except Exception as e:',
  '            os.write(2, ("[r53] dump EXC " + repr(e) + "\\n").encode())',
  '        os.write(2, ("[r53] %s n=%d max=%d nonzero=%d sample=%r\\n" % (tag, n, mx, nz, sample)).encode())',
  '    except Exception as e:',
  '        os.write(2, ("[r53] read EXC tag=%s " % tag + repr(e) + "\\n").encode())',
  'def _tick():',
  '    global _off',
  '    _st["n"] += 1',
  '    if _st["n"] < 25:',
  '        return 0.3',
  '    if _off is None:',
  '        try:',
  '            _off = gpu.types.GPUOffScreen(W, H)',
  '            os.write(2, b"[r53] offscreen created\\n")',
  '        except Exception as e:',
  '            os.write(2, ("[r53] offscreen EXC " + repr(e) + "\\n").encode())',
  '            return None',
  '    if _st["phase"] == 0:',
  '        os.write(2, b"[r53] PHASE0 first read (kick, expect zeros)\\n")',
  '        _do_read("read0")',
  '        _st["phase"] = 1',
  '        return 0.6',
  '    if _st["phase"] == 1:',
  '        os.write(2, b"[r53] PHASE1 second read (fill-late, expect nonzero)\\n")',
  '        _do_read("read1")',
  '        _st["phase"] = 2',
  '        return 0.6',
  '    if _st["phase"] == 2:',
  '        os.write(2, b"[r53] PHASE2 third read (steady, expect nonzero)\\n")',
  '        _do_read("read2")',
  '        os.write(2, b"[r53] DONE\\n")',
  '        return None',
  '    return None',
  'bpy.app.timers.register(_tick, first_interval=1.0)',
].join('\n');

const url = `${BASE}/windowed.html?gate=${GW}x${GH}&pyexpr=${encodeURIComponent(PY)}`;

const logs = [];
let crashed = false;
const browser = await chromium.launch({
  headless: false,
  executablePath: '/Users/paws/Library/Caches/ms-playwright/chromium-1228/chrome-mac-arm64/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing',
  args: ['--enable-unsafe-webgpu', '--use-angle=metal'],
});
const ctx = await browser.newContext({ viewport: { width: GW, height: GH } });
const page = await ctx.newPage();
page.on('console', (m) => {
  const t = m.text();
  logs.push(`[c.${m.type()}] ${t}`);
  if (/table index is out of bounds|RuntimeError|Aborted|abort\(/.test(t)) crashed = true;
});
page.on('pageerror', (e) => { logs.push(`[pageerror] ${e.message}`); if (/table index/.test(e.message)) crashed = true; });

console.log('boot ->', url.slice(0, 90) + '...');
await page.goto(url, { waitUntil: 'domcontentloaded', timeout: BOOT_MS });

const t0 = Date.now();
let done = false;
while (Date.now() - t0 < SETTLE_MS) {
  if (logs.some((l) => l.includes('[r53] DONE'))) { done = true; break; }
  if (crashed) break;
  await page.waitForTimeout(1000);
}
await page.waitForTimeout(3000);

async function pull(name, dest) {
  try {
    const b64 = await page.evaluate((fn) => {
      const m = window.__bwModule;
      if (!m || !m.FS) return null;
      try {
        const d = m.FS.readFile(fn);
        let s = '';
        for (let i = 0; i < d.length; i++) s += String.fromCharCode(d[i]);
        return btoa(s);
      } catch (e) { return 'ERR:' + e.message; }
    }, name);
    if (!b64) { logs.push(`[pull] ${name}: no __bwModule.FS`); return null; }
    if (b64.startsWith('ERR:')) { logs.push(`[pull] ${name}: ${b64}`); return null; }
    const buf = Buffer.from(b64, 'base64');
    writeFileSync(dest, buf);
    logs.push(`[pull] ${name} -> ${dest} (${buf.length} bytes)`);
    return buf.length;
  } catch (e) { logs.push(`[pull] ${name} EXC ${e.message}`); return null; }
}
await pull('/tmp/r53_read0.bin', `${OUT}/r53_read0.bin`);
await pull('/tmp/r53_read1.bin', `${OUT}/r53_read1.bin`);
await pull('/tmp/r53_read2.bin', `${OUT}/r53_read2.bin`);
try { await page.screenshot({ path: `${OUT}/r53_cdp_composite.png` }); logs.push('[cdp] composite saved'); }
catch (e) { logs.push('[cdp] EXC ' + e.message); }

writeFileSync(`${OUT}/probe_console.log`, logs.join('\n') + '\n');
const r53lines = logs.filter((l) => /\[r53\]|\[pull\]|table index|pageerror|\[cdp\]/.test(l));
console.log(`done=${done} crashed=${crashed} logLines=${logs.length}`);
console.log(r53lines.join('\n'));
await browser.close();
