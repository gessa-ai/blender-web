// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: CC0-1.0
//
// M4 r30 — standalone Chrome WebGPU probe. Compiles the EXACT dumped workbench-opaque
// prepass vertex+fragment WGSL (and a trivial positive control) in the SAME bundled
// Chromium the rig uses, builds a render pipeline with layout:'auto', binds identity
// matrices so the vertex maps a hardcoded triangle on-screen, draws it, and reads back
// the object_id (r32uint) target's center pixel. object_id==1 => Chrome rasterized the
// workbench module; ==0 => it did not. getCompilationInfo() is reported for both stages.
//
// Usage: NODE_PATH=/Users/paws/plushly/game-platform/node_modules node standalone_probe.mjs [port]

import { createRequire } from 'module';
import { readFileSync } from 'fs';
const require = createRequire('/Users/paws/plushly/game-platform/node_modules/');
const { chromium } = require('playwright');

const PORT = parseInt(process.argv[2] || '8124', 10);
const DIR = '/Users/paws/blender-web/sandbox/gpu-r30';
const wbV = readFileSync(`${DIR}/workbench_prepass_mesh_opaque_studio_material_no_clip.vertex.wgsl`, 'utf8');
const wbF = readFileSync(`${DIR}/workbench_prepass_mesh_opaque_studio_material_no_clip.fragment.wgsl`, 'utf8');

const browser = await chromium.launch({
  headless: false,
  args: ['--enable-unsafe-webgpu', '--use-angle=metal', '--enable-features=Vulkan'],
});
const page = await browser.newPage();
page.on('console', (m) => console.log('  [page]', m.text()));
page.on('pageerror', (e) => console.log('  [pageerr]', String(e)));
await page.goto(`http://localhost:${PORT}/windowed.html`, { waitUntil: 'domcontentloaded' }).catch(() => {});

const result = await page.evaluate(async ({ wbV, wbF }) => {
  const log = [];
  const out = { steps: [] };
  try {
    if (!navigator.gpu) return { error: 'no navigator.gpu' };
    const adapter = await navigator.gpu.requestAdapter();
    if (!adapter) return { error: 'no adapter' };
    const device = await adapter.requestDevice();
    device.addEventListener('uncapturederror', (e) => log.push('UNCAPTURED: ' + e.error.message));

    async function compInfo(label, code) {
      const mod = device.createShaderModule({ code });
      const info = await mod.getCompilationInfo();
      const msgs = info.messages.map((m) => `${m.type}@${m.lineNum}:${m.linePos} ${m.message}`);
      return { mod, msgs };
    }

    // ---- Trivial positive control: hardcoded triangle, single r32uint target ----
    async function drawProbe(label, vmod, fmod, targets, bindGroupSetup, drawVerts, vbufLayouts, vbufBind, layoutObj) {
      const W = 64, H = 64;
      const colorTexs = targets.map((t) =>
        device.createTexture({ size: [W, H], format: t, usage: GPUTextureUsage.RENDER_ATTACHMENT | GPUTextureUsage.COPY_SRC }));
      const depthTex = device.createTexture({ size: [W, H], format: 'depth32float', usage: GPUTextureUsage.RENDER_ATTACHMENT });
      let pipeline, perr = null;
      try {
        pipeline = await device.createRenderPipelineAsync({
          layout: layoutObj || 'auto',
          vertex: { module: vmod, entryPoint: 'main', buffers: vbufLayouts },
          fragment: { module: fmod, entryPoint: 'main', targets: targets.map((f) => ({ format: f })) },
          primitive: { topology: 'triangle-list', cullMode: 'none' },
          depthStencil: { format: 'depth32float', depthWriteEnabled: true, depthCompare: 'less-equal' },
        });
      } catch (e) { perr = String(e); }
      if (!pipeline) return { label, pipelineError: perr || 'null pipeline' };

      const enc = device.createCommandEncoder();
      const pass = enc.beginRenderPass({
        colorAttachments: colorTexs.map((tx, i) => ({
          view: tx.createView(), clearValue: { r: 0, g: 0, b: 0, a: 0 }, loadOp: 'clear', storeOp: 'store',
        })),
        depthStencilAttachment: { view: depthTex.createView(), depthClearValue: 1.0, depthLoadOp: 'clear', depthStoreOp: 'store' },
      });
      pass.setPipeline(pipeline);
      if (bindGroupSetup) bindGroupSetup(pass, pipeline);
      if (vbufBind) vbufBind(pass);
      pass.draw(drawVerts, 1, 0, 0);
      pass.end();
      // Read back the LAST target (object_id, r32uint) center pixel.
      const idIdx = targets.length - 1;
      const bpr = 256; // r32uint = 4 bytes; padded row = 256
      const rb = device.createBuffer({ size: bpr * H, usage: GPUBufferUsage.COPY_DST | GPUBufferUsage.MAP_READ });
      enc.copyTextureToBuffer({ texture: colorTexs[idIdx] }, { buffer: rb, bytesPerRow: bpr }, [W, H]);
      device.queue.submit([enc.finish()]);
      await rb.mapAsync(GPUMapMode.READ);
      const u = new Uint32Array(rb.getMappedRange().slice(0));
      rb.unmap();
      const cx = 32, cy = 32;
      const center = u[cy * (bpr / 4) + cx];
      // scan for any nonzero
      let nonzero = 0;
      for (let i = 0; i < u.length; i++) if (u[i] !== 0) nonzero++;
      return { label, center, nonzeroPixels: nonzero, targets };
    }

    // Positive control shaders
    const ctrlV = `@vertex fn main(@builtin(vertex_index) vi:u32)->@builtin(position) vec4<f32>{
      var p=array<vec2<f32>,3>(vec2(-0.5,-0.5),vec2(0.5,-0.5),vec2(0.0,0.5));
      return vec4(p[vi],0.5,1.0);}`;
    const ctrlF = `@fragment fn main()->@location(0) u32{ return 1u; }`;
    {
      const v = await compInfo('ctrlV', ctrlV);
      const f = await compInfo('ctrlF', ctrlF);
      out.steps.push({ ctrlV_msgs: v.msgs, ctrlF_msgs: f.msgs });
      const r = await drawProbe('control', v.mod, f.mod, ['r32uint'], null, 3, [], null);
      out.steps.push(r);
    }

    // ---- Workbench modules ----
    const wv = await compInfo('wbV', wbV);
    const wf = await compInfo('wbF', wbF);
    out.steps.push({ wbV_msgs: wv.msgs, wbF_msgs: wf.msgs });

    // Bind group buffers (identity matrices so the triangle lands on-screen).
    const I = [1,0,0,0, 0,1,0,0, 0,0,1,0, 0,0,0,1];
    // binding 2: view uniform = array<ViewMatrices,64>, 256B each. Set [0].viewmat=I, [0].winmat=I.
    const viewBuf = device.createBuffer({ size: 64 * 256, usage: GPUBufferUsage.UNIFORM | GPUBufferUsage.COPY_DST });
    const viewData = new Float32Array(64 * 64);
    viewData.set(I, 0);       // viewmat @ offset 0 floats
    viewData.set(I, 32);      // winmat  @ offset 128 bytes = 32 floats
    device.queue.writeBuffer(viewBuf, 0, viewData);
    // binding 3: matrices storage = array<ObjectMatrices>, model=I, model_inverse=I (128B each)
    const matBuf = device.createBuffer({ size: 4 * 128, usage: GPUBufferUsage.STORAGE | GPUBufferUsage.COPY_DST });
    const matData = new Float32Array(4 * 32); matData.set(I, 0); matData.set(I, 16);
    device.queue.writeBuffer(matBuf, 0, matData);
    // binding 4: res_id storage = array<vec2<u32>>, [0]=(0,0)
    const resBuf = device.createBuffer({ size: 64, usage: GPUBufferUsage.STORAGE | GPUBufferUsage.COPY_DST });
    device.queue.writeBuffer(resBuf, 0, new Uint32Array(16));
    // binding 1: materials storage = array<vec4<f32>>
    const matlBuf = device.createBuffer({ size: 256, usage: GPUBufferUsage.STORAGE | GPUBufferUsage.COPY_DST });
    device.queue.writeBuffer(matlBuf, 0, new Float32Array(64).fill(0.5));
    // binding 0: clipping uniform = array<vec4,6> (96B)
    const clipBuf = device.createBuffer({ size: 96, usage: GPUBufferUsage.UNIFORM | GPUBufferUsage.COPY_DST });
    device.queue.writeBuffer(clipBuf, 0, new Float32Array(24));
    // binding 5: constants uniform (16B)
    const constBuf = device.createBuffer({ size: 16, usage: GPUBufferUsage.UNIFORM | GPUBufferUsage.COPY_DST });
    device.queue.writeBuffer(constBuf, 0, new Uint32Array(4));

    const bufFor = { 0: clipBuf, 1: matlBuf, 2: viewBuf, 3: matBuf, 4: resBuf, 5: constBuf };

    // Vertex buffers: loc0 pos f32x3, loc1 nor f32x3, loc2 ac f32x4, loc3 au f32x2.
    const posBuf = device.createBuffer({ size: 3 * 12, usage: GPUBufferUsage.VERTEX | GPUBufferUsage.COPY_DST });
    device.queue.writeBuffer(posBuf, 0, new Float32Array([-0.5,-0.5,0, 0.5,-0.5,0, 0.0,0.5,0]));
    const norBuf = device.createBuffer({ size: 3 * 12, usage: GPUBufferUsage.VERTEX | GPUBufferUsage.COPY_DST });
    device.queue.writeBuffer(norBuf, 0, new Float32Array([0,0,1, 0,0,1, 0,0,1]));
    const acBuf = device.createBuffer({ size: 3 * 16, usage: GPUBufferUsage.VERTEX | GPUBufferUsage.COPY_DST });
    device.queue.writeBuffer(acBuf, 0, new Float32Array(12).fill(1));
    const auBuf = device.createBuffer({ size: 3 * 8, usage: GPUBufferUsage.VERTEX | GPUBufferUsage.COPY_DST });
    device.queue.writeBuffer(auBuf, 0, new Float32Array(6));

    const vbufLayouts = [
      { arrayStride: 12, attributes: [{ shaderLocation: 0, offset: 0, format: 'float32x3' }] },
      { arrayStride: 12, attributes: [{ shaderLocation: 1, offset: 0, format: 'float32x3' }] },
      { arrayStride: 16, attributes: [{ shaderLocation: 2, offset: 0, format: 'float32x4' }] },
      { arrayStride: 8,  attributes: [{ shaderLocation: 3, offset: 0, format: 'float32x2' }] },
    ];
    const vbufBind = (pass) => {
      pass.setVertexBuffer(0, posBuf); pass.setVertexBuffer(1, norBuf);
      pass.setVertexBuffer(2, acBuf);  pass.setVertexBuffer(3, auBuf);
    };
    // TEST A: auto layout (only bindings Dawn infers as USED = {1,2,3,4}, vertex-only).
    const bindSetupAuto = (pass, pipeline) => {
      const bgl = pipeline.getBindGroupLayout(0);
      const entries = [1, 2, 3, 4].map((b) => ({ binding: b, resource: { buffer: bufFor[b] } }));
      const bg = device.createBindGroup({ layout: bgl, entries });
      pass.setBindGroup(0, bg);
    };
    const rAuto = await drawProbe('workbench_AUTO_layout', wv.mod, wf.mod,
      ['rgba16float', 'rg16float', 'r32uint'], bindSetupAuto, 3, vbufLayouts, vbufBind, undefined);
    out.steps.push(rAuto);

    // TEST B: backend-style EXPLICIT layout — all 6 @binding decls, Vertex|Fragment
    // visibility (mirrors build_explicit_layout scanning both stage WGSLs). Storage=1,3,4.
    const VF = GPUShaderStage.VERTEX | GPUShaderStage.FRAGMENT;
    const explBGL = device.createBindGroupLayout({ entries: [
      { binding: 0, visibility: VF, buffer: { type: 'uniform' } },
      { binding: 1, visibility: VF, buffer: { type: 'read-only-storage' } },
      { binding: 2, visibility: VF, buffer: { type: 'uniform' } },
      { binding: 3, visibility: VF, buffer: { type: 'read-only-storage' } },
      { binding: 4, visibility: VF, buffer: { type: 'read-only-storage' } },
      { binding: 5, visibility: VF, buffer: { type: 'uniform' } },
    ] });
    const explLayout = device.createPipelineLayout({ bindGroupLayouts: [explBGL] });
    const bindSetupExpl = (pass) => {
      const entries = [0,1,2,3,4,5].map((b) => ({ binding: b, resource: { buffer: bufFor[b] } }));
      const bg = device.createBindGroup({ layout: explBGL, entries });
      pass.setBindGroup(0, bg);
    };
    let rExpl;
    try {
      rExpl = await drawProbe('workbench_EXPLICIT_layout', wv.mod, wf.mod,
        ['rgba16float', 'rg16float', 'r32uint'], bindSetupExpl, 3, vbufLayouts, vbufBind, explLayout);
    } catch (e) { rExpl = { label: 'workbench_EXPLICIT_layout', error: String(e) }; }
    out.steps.push(rExpl);

    // TEST C: EXACT backend vertex layout — nor=Unorm10_10_10_2@slot0(Vertex),
    // pos=Float32x3@slot1(Vertex), ac=Float32x4@slot2(INSTANCE dummy), au=Float32x2@slot3
    // (INSTANCE dummy). object_id target = r16uint (backend fmt). Explicit layout.
    const norPacked = device.createBuffer({ size: 3 * 4, usage: GPUBufferUsage.VERTEX | GPUBufferUsage.COPY_DST });
    device.queue.writeBuffer(norPacked, 0, new Uint32Array([0x3ff, 0x3ff, 0x3ff])); // arbitrary packed normals
    const dummyBuf = device.createBuffer({ size: 256, usage: GPUBufferUsage.VERTEX | GPUBufferUsage.COPY_DST });
    device.queue.writeBuffer(dummyBuf, 0, new Float32Array(64));
    const exactLayouts = [
      { arrayStride: 4,  stepMode: 'vertex',   attributes: [{ shaderLocation: 1, offset: 0, format: 'unorm10-10-10-2' }] },
      { arrayStride: 12, stepMode: 'vertex',   attributes: [{ shaderLocation: 0, offset: 0, format: 'float32x3' }] },
      { arrayStride: 16, stepMode: 'instance', attributes: [{ shaderLocation: 2, offset: 0, format: 'float32x4' }] },
      { arrayStride: 8,  stepMode: 'instance', attributes: [{ shaderLocation: 3, offset: 0, format: 'float32x2' }] },
    ];
    const exactBind = (pass) => {
      pass.setVertexBuffer(0, norPacked);
      pass.setVertexBuffer(1, posBuf);
      pass.setVertexBuffer(2, dummyBuf);
      pass.setVertexBuffer(3, dummyBuf);
    };
    let rExact;
    try {
      rExact = await drawProbe('workbench_EXACT_backend_layout', wv.mod, wf.mod,
        ['rgba16float', 'rg16float', 'r32uint'], bindSetupExpl, 3, exactLayouts, exactBind, explLayout);
    } catch (e) { rExact = { label: 'workbench_EXACT_backend_layout', error: String(e) }; }
    out.steps.push(rExact);

    out.uncaptured = log;
    return out;
  } catch (e) {
    return { error: String(e), stack: e.stack, log };
  }
}, { wbV, wbF });

console.log(JSON.stringify(result, null, 2));
await browser.close();
