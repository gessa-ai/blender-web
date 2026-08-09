// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: CC0-1.0

import fs from 'node:fs';
import {createRequire} from 'node:module';

const require = createRequire('/Users/paws/plushly/game-platform/node_modules/');
const {chromium} = require('playwright');

const browser = await chromium.launch({headless: false});
const page = await browser.newPage();
await page.goto('http://127.0.0.1:8143/', {waitUntil: 'load'});
const receipt = await page.evaluate(async () => {
  if (!navigator.gpu) {
    return {error: 'navigator.gpu unavailable'};
  }
  const adapter = await navigator.gpu.requestAdapter({powerPreference: 'high-performance'});
  if (!adapter) {
    return {error: 'requestAdapter returned null'};
  }
  const features = Array.from(adapter.features).sort();
  const limits = {};
  for (const key of Object.keys(Object.getPrototypeOf(adapter.limits))) {
    limits[key] = adapter.limits[key];
  }
  for (const key of ['maxStorageTexturesPerShaderStage',
                     'maxStorageBuffersPerShaderStage']) {
    limits[key] = adapter.limits[key];
  }
  return {
    userAgent: navigator.userAgent,
    features,
    hasTextureFormatsTier1: features.includes('texture-formats-tier1'),
    hasTextureFormatsTier2: features.includes('texture-formats-tier2'),
    limits,
  };
});
const json = JSON.stringify(receipt, null, 2) + '\n';
process.stdout.write(json);
fs.writeFileSync(new URL('./browser-capability-receipt.json', import.meta.url), json);
await browser.close();
