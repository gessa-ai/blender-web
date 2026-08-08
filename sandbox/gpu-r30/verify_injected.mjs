// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: CC0-1.0
// Verify the injected (vertex_index-only) workbench vertex WGSL compiles AND rasterizes
// in standalone Chrome, so the backend force/depthbypass experiments are trustworthy.
import { createRequire } from 'module';
import { readFileSync } from 'fs';
const require = createRequire('/Users/paws/plushly/game-platform/node_modules/');
const { chromium } = require('playwright');
const DIR = '/Users/paws/blender-web/sandbox/gpu-r30';
const vwgsl = readFileSync(`${DIR}/injected_vertex.wgsl`, 'utf8');
const fwgsl = readFileSync(`${DIR}/workbench_prepass_mesh_opaque_studio_material_no_clip.fragment.wgsl`, 'utf8');
const browser = await chromium.launch({ headless: false, args: ['--enable-unsafe-webgpu'] });
const page = await browser.newPage();
page.on('console', (m) => console.log('  [page]', m.text()));
await page.goto('http://localhost:8124/windowed.html', { waitUntil: 'domcontentloaded' }).catch(()=>{});
const r = await page.evaluate(async ({ vwgsl, fwgsl }) => {
  const adapter = await navigator.gpu.requestAdapter();
  const device = await adapter.requestDevice();
  const log = [];
  device.addEventListener('uncapturederror', (e) => log.push('UNCAPTURED: ' + e.error.message));
  const vm = device.createShaderModule({ code: vwgsl });
  const fm = device.createShaderModule({ code: fwgsl });
  const vi = await vm.getCompilationInfo();
  const fi = await fm.getCompilationInfo();
  const vmsg = vi.messages.map((m) => `${m.type}@${m.lineNum}: ${m.message}`);
  const fmsg = fi.messages.map((m) => `${m.type}@${m.lineNum}: ${m.message}`);
  // Draw with Draw(3) using layout:'auto'; the injected vertex ignores all binds for
  // position, but still DECLARES binds -> auto layout may require them. Bind dummies.
  const W = 64, H = 64;
  const tex = ['rgba16float','rg16float','r32uint'].map((f)=>device.createTexture({size:[W,H],format:f,usage:GPUTextureUsage.RENDER_ATTACHMENT|GPUTextureUsage.COPY_SRC}));
  const dep = device.createTexture({size:[W,H],format:'depth32float',usage:GPUTextureUsage.RENDER_ATTACHMENT});
  let pipe, perr=null;
  try {
    pipe = await device.createRenderPipelineAsync({
      layout:'auto',
      vertex:{ module: vm, entryPoint:'main', buffers: [
        { arrayStride: 12, stepMode:'vertex', attributes:[{shaderLocation:0,offset:0,format:'float32x3'}] },
        { arrayStride: 12, stepMode:'vertex', attributes:[{shaderLocation:1,offset:0,format:'float32x3'}] },
        { arrayStride: 16, stepMode:'instance', attributes:[{shaderLocation:2,offset:0,format:'float32x4'}] },
        { arrayStride: 8,  stepMode:'instance', attributes:[{shaderLocation:3,offset:0,format:'float32x2'}] },
      ] },
      fragment:{ module: fm, entryPoint:'main', targets: [{format:'rgba16float'},{format:'rg16float'},{format:'r32uint'}] },
      primitive:{ topology:'triangle-list', cullMode:'none' },
      depthStencil:{ format:'depth32float', depthWriteEnabled:true, depthCompare:'always' },
    });
  } catch(e){ perr = String(e); }
  if (!pipe) return { vmsg, fmsg, pipelineError: perr || 'null' };
  // Determine required bind group entries from auto layout by binding dummies for the
  // vertex-visible storage/uniform bindings the module still declares.
  const mkU = (n)=>{const b=device.createBuffer({size:n,usage:GPUBufferUsage.UNIFORM|GPUBufferUsage.COPY_DST});device.queue.writeBuffer(b,0,new Uint8Array(n));return b;};
  const mkS = (n)=>{const b=device.createBuffer({size:n,usage:GPUBufferUsage.STORAGE|GPUBufferUsage.COPY_DST});device.queue.writeBuffer(b,0,new Uint8Array(n));return b;};
  const bufFor = { 0: mkU(96), 1: mkS(256), 2: mkU(64*256), 3: mkS(512), 4: mkS(64), 5: mkU(16) };
  const enc = device.createCommandEncoder();
  const pass = enc.beginRenderPass({
    colorAttachments: tex.map((t)=>({view:t.createView(),clearValue:{r:0,g:0,b:0,a:0},loadOp:'clear',storeOp:'store'})),
    depthStencilAttachment:{view:dep.createView(),depthClearValue:1.0,depthLoadOp:'clear',depthStoreOp:'store'},
  });
  pass.setPipeline(pipe);
  // The injected vertex uses bindings 1,2,3,4 (main_inner still runs). Bind them.
  const bgl = pipe.getBindGroupLayout(0);
  let bgErr=null, bg=null;
  for (const set of [[1,2,3,4],[0,1,2,3,4,5],[1,2,3,4,5],[0,1,2,3,4]]) {
    try { bg = device.createBindGroup({layout:bgl, entries:set.map((b)=>({binding:b,resource:{buffer:bufFor[b]}}))}); break; }
    catch(e){ bgErr = String(e); }
  }
  if (!bg) return { vmsg, fmsg, bindGroupError: bgErr };
  pass.setBindGroup(0, bg);
  const vb = device.createBuffer({ size: 3*16, usage: GPUBufferUsage.VERTEX|GPUBufferUsage.COPY_DST });
  device.queue.writeBuffer(vb, 0, new Float32Array(12));
  pass.setVertexBuffer(0, vb); pass.setVertexBuffer(1, vb);
  pass.setVertexBuffer(2, vb); pass.setVertexBuffer(3, vb);
  pass.draw(3,1,0,0);
  pass.end();
  const bpr=256; const rb=device.createBuffer({size:bpr*H,usage:GPUBufferUsage.COPY_DST|GPUBufferUsage.MAP_READ});
  enc.copyTextureToBuffer({texture:tex[2]},{buffer:rb,bytesPerRow:bpr},[W,H]);
  device.queue.submit([enc.finish()]);
  await rb.mapAsync(GPUMapMode.READ);
  const u=new Uint32Array(rb.getMappedRange().slice(0)); rb.unmap();
  let nz=0; for(let i=0;i<u.length;i++) if(u[i]!==0) nz++;
  return { vmsg, fmsg, center: u[32*(bpr/4)+32], nonzeroPixels: nz, uncaptured: log };
}, { vwgsl, fwgsl });
console.log(JSON.stringify(r, null, 2));
await browser.close();
