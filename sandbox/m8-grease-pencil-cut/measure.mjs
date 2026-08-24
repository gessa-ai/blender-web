#!/usr/bin/env node
// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: GPL-2.0-or-later

import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { brotliCompressSync, constants } from "node:zlib";

if (process.argv.length !== 3) {
  console.error("usage: measure.mjs WASM");
  process.exit(2);
}

const path = process.argv[2];
const bytes = readFileSync(path);
function brotliSize(quality) {
  return brotliCompressSync(bytes, {
    params: { [constants.BROTLI_PARAM_QUALITY]: quality },
  }).byteLength;
}

console.log(JSON.stringify({
  path,
  node: process.versions.node,
  sha256: createHash("sha256").update(bytes).digest("hex"),
  raw_bytes: bytes.byteLength,
  brotli_q5_bytes: brotliSize(5),
  brotli_q11_bytes: brotliSize(11),
}));
