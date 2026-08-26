// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: GPL-2.0-or-later
//
// Diagnostic-only fallback-adapter capture for P0-G. This binds no receipt.

import { createRequire } from "node:module";
import { mkdirSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "../..");
const outDir = resolve(root, "sandbox/p0-widget-shadow/artifacts");
mkdirSync(outDir, { recursive: true });

const moduleRoots = [
  process.env.BW_NODE_MODULES,
  resolve(root, ".m4-node/node_modules"),
].filter(Boolean);
let chromium = null;
for (const candidate of moduleRoots) {
  try {
    chromium = createRequire(resolve(candidate, "package.json"))("playwright").chromium;
    break;
  }
  catch (_) {}
}
if (!chromium) {
  throw new Error(`playwright is unavailable; checked ${moduleRoots.join(", ")}`);
}

const port = Number(process.argv[2] || 8123);
const consoleLines = [];
const pageErrors = [];
let nextProbeId = 1;

async function installWorkerProbe(worker) {
  const probeId = nextProbeId++;
  await worker.evaluate((probeId) => {
    if (self.__bwP0GWidgetProbeInstalled || typeof GPUDevice === "undefined") {
      return;
    }
    self.__bwP0GWidgetProbeInstalled = true;
    const widgetModules = new WeakSet();
    const widgetPipelines = new WeakSet();
    const widgetPasses = new WeakSet();
    const textureInfo = new WeakMap();
    const viewTexture = new WeakMap();
    const bufferInfo = new WeakMap();
    const bindGroupInfo = new WeakMap();
    const passInfo = new WeakMap();
    const texturePassHistory = new WeakMap();
    const mappedRanges = new WeakMap();
    const devicePrototype = GPUDevice.prototype;
    const createShaderModule = devicePrototype.createShaderModule;
    const createRenderPipeline = devicePrototype.createRenderPipeline;
    const createTexture = devicePrototype.createTexture;
    const createBuffer = devicePrototype.createBuffer;
    const createBindGroup = devicePrototype.createBindGroup;
    const createView = GPUTexture.prototype.createView;
    const beginRenderPass = GPUCommandEncoder.prototype.beginRenderPass;
    const setPipeline = GPURenderPassEncoder.prototype.setPipeline;
    const setBindGroup = GPURenderPassEncoder.prototype.setBindGroup;
    const writeBuffer = GPUQueue.prototype.writeBuffer;
    const getMappedRange = GPUBuffer.prototype.getMappedRange;
    const unmap = GPUBuffer.prototype.unmap;
    let pushWriteCount = 0;
    let nextTextureId = 1;
    let nextBufferId = 1;
    const trace = (kind, payload) => {
      console.log(`[P0G] ${kind} ${JSON.stringify({probeId, ...payload})}`);
    };

    devicePrototype.createTexture = function (descriptor) {
      const texture = createTexture.call(this, descriptor);
      textureInfo.set(texture, {
        id: nextTextureId++,
        label: String(descriptor?.label || ""),
        format: String(descriptor?.format),
        size: descriptor?.size,
        usage: Number(descriptor?.usage),
      });
      return texture;
    };

    GPUTexture.prototype.createView = function (descriptor) {
      const view = createView.call(this, descriptor);
      viewTexture.set(view, this);
      return view;
    };

    devicePrototype.createBuffer = function (descriptor) {
      const buffer = createBuffer.call(this, descriptor);
      bufferInfo.set(buffer, {
        id: nextBufferId++,
        label: String(descriptor?.label || ""),
        size: Number(descriptor?.size),
        usage: Number(descriptor?.usage),
      });
      return buffer;
    };

    devicePrototype.createBindGroup = function (descriptor) {
      const group = createBindGroup.call(this, descriptor);
      bindGroupInfo.set(group, Array.from(descriptor?.entries || [], (entry) => ({
        binding: Number(entry.binding),
        buffer: entry.resource?.buffer ? bufferInfo.get(entry.resource.buffer) || null : null,
        offset: Number(entry.resource?.offset || 0),
        size: Number(entry.resource?.size || 0),
      })));
      return group;
    };

    GPUBuffer.prototype.getMappedRange = function (...args) {
      const range = getMappedRange.call(this, ...args);
      mappedRanges.set(this, range);
      return range;
    };

    GPUBuffer.prototype.unmap = function () {
      const info = bufferInfo.get(this);
      const range = mappedRanges.get(this);
      if (info?.label === "push-constant buffer creation" && info.size === 144 && range) {
        const floats = Array.from(new Float32Array(range), (value) =>
          Number.isFinite(value) ? Number(value.toFixed(5)) : String(value));
        trace("push-map", {info, floats});
      }
      return unmap.call(this);
    };

    GPUCommandEncoder.prototype.beginRenderPass = function (descriptor) {
      const pass = beginRenderPass.call(this, descriptor);
      const info = {
        label: String(descriptor?.label || ""),
        colors: Array.from(descriptor?.colorAttachments || [], (attachment) => {
          const texture = viewTexture.get(attachment?.view);
          const color = {
            textureObject: texture || null,
            texture: texture ? textureInfo.get(texture) || null : null,
            loadOp: String(attachment?.loadOp),
            storeOp: String(attachment?.storeOp),
            clearValue: attachment?.clearValue || null,
          };
          if (texture) {
            const history = texturePassHistory.get(texture) || [];
            history.push({
              loadOp: color.loadOp,
              storeOp: color.storeOp,
              clearValue: color.clearValue,
            });
            if (history.length > 12) history.shift();
            texturePassHistory.set(texture, history);
          }
          return color;
        }),
      };
      passInfo.set(pass, info);
      return pass;
    };

    devicePrototype.createShaderModule = function (descriptor) {
      const code = String(descriptor?.code || "");
      const isWidgetShadow = code.includes("shadowFalloff") && code.includes("innerMask") &&
        code.includes("0.722");
      const module = createShaderModule.call(this, descriptor);
      if (isWidgetShadow) {
        widgetModules.add(module);
        const relevant = code.split("\n").filter((line) =>
          /shadow|inner|frag|output|return|0\.722|0\.277|vec4/.test(line));
        trace("widget-wgsl", {relevant});
      }
      return module;
    };

    devicePrototype.createRenderPipeline = function (descriptor) {
      if (widgetModules.has(descriptor?.fragment?.module)) {
        const targets = Array.from(descriptor.fragment.targets || [], (target) => ({
          format: String(target?.format),
          writeMask: Number(target?.writeMask),
          blend: target?.blend ? {
            color: {
              operation: String(target.blend.color?.operation),
              srcFactor: String(target.blend.color?.srcFactor),
              dstFactor: String(target.blend.color?.dstFactor),
            },
            alpha: {
              operation: String(target.blend.alpha?.operation),
              srcFactor: String(target.blend.alpha?.srcFactor),
              dstFactor: String(target.blend.alpha?.dstFactor),
            },
          } : null,
        }));
        trace("widget-pipeline", {
          targets,
          topology: String(descriptor.primitive?.topology),
          stripIndexFormat: String(descriptor.primitive?.stripIndexFormat),
        });
      }
      const pipeline = createRenderPipeline.call(this, descriptor);
      if (widgetModules.has(descriptor?.fragment?.module)) {
        widgetPipelines.add(pipeline);
      }
      return pipeline;
    };

    GPURenderPassEncoder.prototype.setPipeline = function (pipeline) {
      if (widgetPipelines.has(pipeline)) {
        widgetPasses.add(this);
        const info = passInfo.get(this) || null;
        const serialInfo = info ? {
          label: info.label,
          colors: info.colors.map(({ textureObject, ...color }) => color),
        } : null;
        const history = info?.colors?.map((color) => ({
          textureId: color.texture?.id ?? null,
          history: color.textureObject ? texturePassHistory.get(color.textureObject) || [] : [],
        }));
        trace("widget-pass", {info: serialInfo, history});
      }
      return setPipeline.call(this, pipeline);
    };

    GPURenderPassEncoder.prototype.setBindGroup = function (index, group, ...rest) {
      if (widgetPasses.has(this)) {
        trace("widget-bind-group", {
          index: Number(index),
          entries: bindGroupInfo.get(group) || null,
        });
      }
      return setBindGroup.call(this, index, group, ...rest);
    };

    GPUQueue.prototype.writeBuffer = function (buffer, bufferOffset, data, dataOffset, size) {
      const info = bufferInfo.get(buffer);
      if (info?.label === "push-constant buffer creation" && info.size === 144 &&
          pushWriteCount < 120) {
        const sourceOffset = Number(dataOffset || 0);
        const sourceSize = Number(size ?? (data.byteLength - sourceOffset));
        const bytes = new Uint8Array(data.buffer, data.byteOffset + sourceOffset, sourceSize);
        const aligned = bytes.byteLength - (bytes.byteLength % 4);
        const floats = Array.from(
          new Float32Array(bytes.buffer, bytes.byteOffset, aligned / 4),
          (value) => Number.isFinite(value) ? Number(value.toFixed(5)) : String(value),
        );
        trace("push-write", {
          count: pushWriteCount++,
          bufferOffset: Number(bufferOffset),
          info,
          floats,
        });
      }
      return writeBuffer.call(this, buffer, bufferOffset, data, dataOffset, size);
    };
  }, probeId);
}

const browser = await chromium.launch({
  headless: false,
  args: [
    "--enable-unsafe-webgpu",
    "--use-webgpu-adapter=swiftshader",
    "--use-gpu-in-tests",
    ...(process.platform === "linux" && process.env.DISPLAY ? ["--ozone-platform=x11"] : []),
  ],
});

try {
  const context = await browser.newContext({
    viewport: { width: 1280, height: 720 },
    deviceScaleFactor: 1,
  });
  const page = await context.newPage();
  page.on("worker", (worker) => {
    installWorkerProbe(worker).catch((error) => {
      consoleLines.push(`[P0G] worker-probe-error ${error.message}`);
    });
  });
  page.on("console", (message) => consoleLines.push(message.text()));
  page.on("pageerror", (error) => pageErrors.push(`${error.name}: ${error.message}`));

  await page.goto(`http://127.0.0.1:${port}/windowed.html?gate=1280x720`, {
    waitUntil: "domcontentloaded",
    timeout: 180000,
  });
  await page.waitForFunction(() => document.querySelector("#state")?.dataset.state === "running", {
    timeout: 180000,
    polling: 250,
  });
  await page.waitForFunction(() => Number(window.__bwModule?._bw_wm_tick_count?.()) >= 2, {
    timeout: 30000,
    polling: 250,
  });
  await page.waitForTimeout(4000);

  const canvas = page.locator("#canvas");
  await canvas.focus();
  await page.keyboard.press("Escape");
  await page.waitForTimeout(1000);
  await canvas.screenshot({ path: resolve(outDir, "workspace.png") });

  const box = await canvas.boundingBox();
  if (!box) {
    throw new Error("canvas has no bounding box");
  }
  await page.mouse.move(box.x + 30, box.y + 400);
  await page.waitForTimeout(1500);
  await canvas.screenshot({ path: resolve(outDir, "toolbar-hover.png") });

  const diagnostic = {
    state: await page.evaluate(() => document.querySelector("#state")?.dataset.state || null),
    ticks: await page.evaluate(() => Number(window.__bwModule?._bw_wm_tick_count?.() ?? -1)),
    presents: await page.evaluate(() => Number(window.__bwModule?._bw_present_count?.() ?? -1)),
    p0gLines: consoleLines.filter((line) => line.startsWith("[P0G]")),
    pageErrors,
  };
  writeFileSync(resolve(outDir, "diagnostic.json"), `${JSON.stringify(diagnostic, null, 2)}\n`);
  console.log(`P0G_DIAGNOSTIC_DONE p0g_lines=${diagnostic.p0gLines.length} ` +
    `page_errors=${pageErrors.length} ticks=${diagnostic.ticks} presents=${diagnostic.presents}`);
}
finally {
  await browser.close();
}
