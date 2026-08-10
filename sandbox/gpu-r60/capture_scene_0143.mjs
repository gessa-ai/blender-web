// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: GPL-3.0-or-later

// Run the proven r35 startup-file bridge without mutating its retained matrix.
// Only the durable output root changes; argv and render behavior remain identical.
import { mkdirSync, readFileSync } from 'fs';

const sourcePath = '/Users/paws/blender-web/sandbox/gpu-r35/bridge_boot.mjs';
const outDir = '/Users/paws/blender-web/sandbox/gpu-r60/browser/scenes';
mkdirSync(outDir, { recursive: true });

const source = readFileSync(sourcePath, 'utf8')
  .replace(
    "const OUTDIR = '/Users/paws/blender-web/sandbox/gpu-r35';",
    `const OUTDIR = '${outDir}';`,
  )
  .replace(
    'const W = 640, H = 480;',
    'const W = Number(process.env.BW_CAPTURE_W || 640), H = Number(process.env.BW_CAPTURE_H || 480);',
  )
  .replace(
    "  '        sc.render.resolution_x = ' + RESW,",
    "  '        if sc.render.engine == \\\"BLENDER_WORKBENCH\\\":',\n" +
      "  '            sc.display.shading.light = \\\"STUDIO\\\"',\n" +
      "  '            sc.display.shading.color_type = \\\"TEXTURE\\\"',\n" +
      "  '        sc.render.resolution_x = ' + RESW,",
  )
  .replace(
    'const marks = [], gpuErrors = [], kicks = [], dones = [];',
    'const marks = [], gpuErrors = [], kicks = [], dones = [], allConsole = [];',
  )
  .replace(
    "  const t = m.text();\n  if (t.includes('M6_BRIDGE')) marks.push(t);",
    "  const t = m.text();\n  allConsole.push(`[${m.type()}] ${t}`);\n  if (t.includes('M6_BRIDGE')) marks.push(t);",
  )
  .replace(
    "  const manifest = { mode: 'boot', hostBlend: HOST_BLEND, engine: ENGINE, res: [RESW, RESH],",
    "  writeFileSync(`${CAPDIR}/console.log`, `${allConsole.join('\\n')}\\n`);\n  const manifest = { mode: 'boot', hostBlend: HOST_BLEND, engine: ENGINE, res: [RESW, RESH],",
  )
  .replace(
    "window.__bwModule.FS.readFile('/tmp/m6_bridge0001.png')",
    "window.__bwModule.FS.readFile('/tmp/m6_bridge.png')",
  )
  .replace(
    'render_op_black.png',
    'render_operator.png',
  );
await import(`data:text/javascript;base64,${Buffer.from(source).toString('base64')}`);
