// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: GPL-3.0-or-later

// Run the proven r52 fixed-gate UI capture without mutating its retained evidence.
// The harness has no relative imports, so replacing only its output root preserves
// its browser and capture behavior byte-for-byte.
import { mkdirSync, readFileSync } from 'fs';

const sourcePath = '/Users/paws/blender-web/sandbox/gpu-r52/capture_splash.mjs';
const outDir = '/Users/paws/blender-web/sandbox/gpu-r60/browser/ui';
mkdirSync(outDir, { recursive: true });

const source = readFileSync(sourcePath, 'utf8').replace(
  "const OUTDIR = '/Users/paws/blender-web/sandbox/gpu-r52/splash';",
  `const OUTDIR = '${outDir}';`,
);
await import(`data:text/javascript;base64,${Buffer.from(source).toString('base64')}`);
