#!/usr/bin/env node
// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: GPL-3.0-or-later
//
// Deterministic public-bundle Brotli codec. The launch wire contract is tied to
// Emscripten's pinned Node so an ambient host encoder cannot silently change the
// release bytes. lgwin=24 is Brotli's standard 16 MiB window (not large-window
// extension mode) and materially improves the profile-split Wasm primary.

"use strict";

import assert from "node:assert/strict";
import {createHash} from "node:crypto";
import {readFileSync, writeFileSync} from "node:fs";
import {resolve} from "node:path";
import {
  brotliCompressSync,
  brotliDecompressSync,
  constants as zlibConstants,
} from "node:zlib";

const PINNED_NODE_VERSION = "v22.16.0";
const QUALITY = 11;
const LGWIN = 24;

function fail(message) {
  console.error(`brotli_q11: FATAL: ${message}`);
  process.exit(1);
}

function requirePinnedNode() {
  if (process.version !== PINNED_NODE_VERSION) {
    fail(`Node ${PINNED_NODE_VERSION} required, got ${process.version}`);
  }
}

function encode(source) {
  return brotliCompressSync(source, {
    params: {
      [zlibConstants.BROTLI_PARAM_QUALITY]: QUALITY,
      [zlibConstants.BROTLI_PARAM_LGWIN]: LGWIN,
    },
  });
}

function encodeFile(input, output) {
  if (resolve(input) === resolve(output)) fail("input and output paths are identical");
  const source = readFileSync(input);
  const compressed = encode(source);
  writeFileSync(output, compressed);
  console.log(
    `BW_BROTLI_Q11_ENCODE bytes=${source.length} compressed=${compressed.length} ` +
    `quality=${QUALITY} lgwin=${LGWIN}`,
  );
}

function decodeToStdout(input) {
  const decoded = brotliDecompressSync(readFileSync(input));
  process.stdout.write(decoded);
}

function selfcheck() {
  // Put the same high-entropy block more than 4 MiB apart. The legacy default
  // lgwin=22 cannot refer back to it; the release lgwin=24 can. Exact output
  // identities pin both the parameters and Node's Brotli implementation.
  const seed = Buffer.alloc(96 * 1024);
  let state = 0x6d2b79f5;
  for (let index = 0; index < seed.length; index++) {
    state ^= state << 13;
    state ^= state >>> 17;
    state ^= state << 5;
    seed[index] = state & 0xff;
  }
  const fixture = Buffer.concat([seed, Buffer.alloc((1 << 22) + 4096, 0x5a), seed]);
  const compressed = encode(fixture);
  const legacy = brotliCompressSync(fixture, {
    params: {
      [zlibConstants.BROTLI_PARAM_QUALITY]: 11,
      [zlibConstants.BROTLI_PARAM_LGWIN]: 22,
    },
  });
  assert.deepEqual(brotliDecompressSync(compressed), fixture);
  assert.equal(compressed.length, 98334);
  assert.equal(legacy.length, 197282);
  assert.equal(
    createHash("sha256").update(compressed).digest("hex"),
    "a5077aeebb2f4d96af19e64de3de26a11b56382106d3db388dccf400ff82ef62",
  );
  assert.ok(legacy.length - compressed.length >= 90000);
  const qualityFixture = Buffer.from(Array.from(
    {length: 20000},
    (_, index) =>
      `shader binding ${index % 257} group ${index % 7} pipeline ${(index * index) % 100003}\n`,
  ).join(""));
  const qualityCompressed = encode(qualityFixture);
  assert.deepEqual(brotliDecompressSync(qualityCompressed), qualityFixture);
  assert.equal(qualityCompressed.length, 55882);
  assert.equal(
    createHash("sha256").update(qualityCompressed).digest("hex"),
    "a53bfbb67027bfc055a2c4aae387dc6e19376a190f0cd3eda3c3656c0b996b83",
  );
  console.log(
    `BW_BROTLI_Q11_SELFCHECK_PASS node=${process.version} quality=${QUALITY} ` +
    `lgwin=${LGWIN} fixture=${fixture.length} delta=${legacy.length - compressed.length}`,
  );
}

requirePinnedNode();
const [command, ...args] = process.argv.slice(2);
if (command === "encode" && args.length === 2) {
  encodeFile(args[0], args[1]);
}
else if (command === "decode-stdout" && args.length === 1) {
  decodeToStdout(args[0]);
}
else if (command === "--selfcheck" && args.length === 0) {
  selfcheck();
}
else {
  fail("usage: brotli_q11.mjs encode INPUT OUTPUT | decode-stdout INPUT | --selfcheck");
}
