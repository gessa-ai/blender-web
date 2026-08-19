// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: GPL-3.0-or-later
// Build and run a browser executable linked to the shipping BLI TaskPool implementation.
import { spawn, spawnSync } from 'child_process';
import { createHash } from 'crypto';
import { createRequire } from 'module';
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'fs';
import { dirname, join, resolve } from 'path';
import { createServer } from 'net';
import { fileURLToPath } from 'url';

const here=dirname(fileURLToPath(import.meta.url)); const repo=resolve(here,'..','..','..');
const build=join(repo,'build-wasm-windowed-opt');
const target=join(build,'bin/tests/BLI_task_web_lifecycle.js');
const wasmPath=join(build,'bin/tests/BLI_task_web_lifecycle.wasm');
const buildCommand=['ninja','-C',build,'BLI_task_web_lifecycle','-j2'];
const linkFlags=['-pthread','-sPROXY_TO_PTHREAD=1','-sPTHREAD_POOL_SIZE=8','-sEXIT_RUNTIME=1','-sALLOW_MEMORY_GROWTH=1','-sINITIAL_MEMORY=134217728','-Wno-pthreads-mem-growth','-sWASM_BIGINT=1','-sNODERAWFS=0','-sSTACK_SIZE=33554432','-sDEFAULT_PTHREAD_STACK_SIZE=8388608'];
const ninja=spawnSync(buildCommand[0],buildCommand.slice(1),{encoding:'utf8',timeout:600000});
if(ninja.status!==0) throw new Error(ninja.stdout+ninja.stderr);
if(!existsSync(target)||!existsSync(wasmPath)) throw new Error('BLI_task_web_lifecycle artifacts absent');
const commandGraph=spawnSync('ninja',['-C',build,'-t','commands','BLI_task_web_lifecycle'],{encoding:'utf8'});
if(commandGraph.status!==0)throw new Error(commandGraph.stdout+commandGraph.stderr);
const linkCommands=commandGraph.stdout.split('\n').filter(line=>line.includes('BLI_task_web_lifecycle.js')&&line.includes('-sPROXY_TO_PTHREAD=1'));
if(linkCommands.length!==1)throw new Error(`expected one lifecycle link command, found ${linkCommands.length}`);
const actualLinkCommand=linkCommands[0];
const stackOccurrences=[...actualLinkCommand.matchAll(/-sSTACK_SIZE=(\d+)/g)].map(match=>Number(match[1]));
const defaultStackOccurrences=[...actualLinkCommand.matchAll(/-sDEFAULT_PTHREAD_STACK_SIZE=(\d+)/g)].map(match=>Number(match[1]));
const linkStackPolicyPass=stackOccurrences.at(-1)===33554432&&defaultStackOccurrences.at(-1)===8388608;
const html=join(build,'bin/tests/BLI_task_web_lifecycle.html');
writeFileSync(html,'<!doctype html><meta charset=utf-8><pre id=o></pre><script>globalThis.__bwWorkerConstructors=0;const BW=Worker;globalThis.Worker=function(...a){globalThis.__bwWorkerConstructors++;return new BW(...a)};globalThis.Worker.prototype=BW.prototype;var Module={print:t=>o.textContent+=t+"\\n",printErr:t=>o.textContent+=t+"\\n"};</script><script src=BLI_task_web_lifecycle.js></script>');
const evidenceRoot=join(here,'evidence'); mkdirSync(evidenceRoot,{recursive:true});
const label=process.argv[2];
if(!label||!/^[a-z0-9][a-z0-9._-]*$/.test(label))throw new Error('immutable evidence label argument required');
const out=join(evidenceRoot,label);
if(existsSync(out))throw new Error(`refusing existing immutable evidence label ${out}`);
mkdirSync(out);
const serverLog=join(out,'server.jsonl'); const receiptPath=join(out,'receipt.json');
const port=await new Promise((resolvePort,reject)=>{const socket=createServer();socket.once('error',reject);socket.listen(0,'127.0.0.1',()=>{const address=socket.address();socket.close(error=>error?reject(error):resolvePort(address.port));});});
let server=null; let browser=null; let body=''; let workerConstructorCount=null; let listenerProof=''; let runError=null;
const consoleLines=[]; const serverStdout=[]; const serverStderr=[];
try {
  server=spawn('python3',[join(repo,'sandbox/m8-wasm-split/serve_split.py'),String(port),join(build,'bin/tests'),serverLog],{stdio:['ignore','pipe','pipe']});
  server.stdout.on('data',chunk=>serverStdout.push(String(chunk)));
  server.stderr.on('data',chunk=>serverStderr.push(String(chunk)));
  let ready=false;
  for(let i=0;i<100;i++){
    if(server.exitCode!==null)throw new Error(`server exited ${server.exitCode}: ${serverStderr.join('')}`);
    try{const response=await fetch(`http://127.0.0.1:${port}/BLI_task_web_lifecycle.html`);if(response.ok){ready=true;break;}}catch{}
    await new Promise(r=>setTimeout(r,50));
  }
  if(!ready)throw new Error('server readiness timeout');
  const listener=spawnSync('lsof',['-nP','-a','-p',String(server.pid),`-iTCP:${port}`,'-sTCP:LISTEN'],{encoding:'utf8'});
  listenerProof=listener.stdout;
  if(listener.status!==0||!listenerProof.includes(String(server.pid))||!listenerProof.includes(`:${port}`)){
    throw new Error(`spawned server does not own listener: ${listener.stderr||listener.stdout}`);
  }
  const modules='/Users/paws/plushly/game-platform/node_modules';
  const {chromium}=createRequire(join(modules,'package.json'))('playwright'); browser=await chromium.launch({headless:true});
  const page=await browser.newPage(); page.on('console',m=>consoleLines.push(m.text()));
  page.on('pageerror',error=>consoleLines.push(`PAGEERROR ${error}`));
  page.on('requestfailed',request=>consoleLines.push(`REQUESTFAILED ${request.url()} ${request.failure()?.errorText}`));
  await page.goto(`http://127.0.0.1:${port}/BLI_task_web_lifecycle.html`);
  await page.waitForFunction(()=>document.body.innerText.includes('BW_PTHREAD_LIFECYCLE_RESULT '),null,{timeout:120000});
  body=await page.locator('body').innerText(); workerConstructorCount=await page.evaluate(()=>globalThis.__bwWorkerConstructors).catch(()=>null);
}catch(error){runError=String(error?.stack||error);}
finally{
  if(browser)await browser.close().catch(()=>{});
  if(server&&server.exitCode===null){server.kill('SIGTERM');await new Promise(resolveClose=>{const timer=setTimeout(resolveClose,2000);server.once('exit',()=>{clearTimeout(timer);resolveClose();});});}
}
let outputRows=[];
try{outputRows=body.split('\n').filter(line=>line.includes('BW_PTHREAD_LIFECYCLE ')).map(line=>JSON.parse(line.split('BW_PTHREAD_LIFECYCLE ')[1]));}
catch(error){runError??=`lifecycle row parse failed: ${error}`;}
let stackPolicy=null;
try {
  const rows=body.split('\n').filter(line=>line.includes('BW_PTHREAD_STACK_POLICY '));
  if(rows.length===1)stackPolicy=JSON.parse(rows[0].split('BW_PTHREAD_STACK_POLICY ')[1]);
} catch(error){runError??=`stack-policy row parse failed: ${error}`;}
const bootstrapRows=outputRows.filter(row=>row.phase==='bootstrap'); const readyRows=outputRows.filter(row=>row.phase==='ready');
const rowsPass=outputRows.length===4&&bootstrapRows.length===2&&new Set(bootstrapRows.map(row=>row.serial)).size===2&&
  bootstrapRows.every(row=>Number.isInteger(row.workers_before)&&row.workers_before>=1&&row.workers_after===row.workers_before&&
    Number.isInteger(row.constructors_before)&&row.constructors_after===row.constructors_before)&&readyRows.length===2&&
  new Set(readyRows.map(row=>row.serial)).size===2&&readyRows.every(row=>Number.isInteger(row.workers_before)&&
    row.workers_before>=1&&row.workers_after>=row.workers_before&&Number.isInteger(row.constructors_before)&&
    row.constructors_after>=row.constructors_before);
const stackPolicyPass=stackPolicy?.proxy_main===33554432&&stackPolicy?.ordinary_default===8388608;
const pass=runError===null&&body.includes('BW_PTHREAD_LIFECYCLE_RESULT PASS')&&rowsPass&&stackPolicyPass&&linkStackPolicyPass&&Number.isInteger(workerConstructorCount)&&workerConstructorCount>=1;
const sha=p=>createHash('sha256').update(readFileSync(p)).digest('hex');
const receipt={schema:'blender-web.pthread-lifecycle.v3',status:pass?'PASS':'FAIL',label,port,serverPid:server?.pid??null,listenerProof,runError,body,consoleLines,serverStdout,serverStderr,outputRows,rowsPass,stackPolicy,stackPolicyPass,
  workerConstructorCount,target:{path:target,sha256:sha(target)},wasm:{path:wasmPath,sha256:sha(wasmPath)},testSource:{path:join(repo,'upstream/source/blender/blenlib/tests/BLI_task_web_lifecycle.cc'),sha256:sha(join(repo,'upstream/source/blender/blenlib/tests/BLI_task_web_lifecycle.cc'))},
  taskPoolSource:{path:join(repo,'upstream/source/blender/blenlib/intern/task_pool.cc'),sha256:sha(join(repo,'upstream/source/blender/blenlib/intern/task_pool.cc'))},
  driver:{path:fileURLToPath(import.meta.url),sha256:sha(fileURLToPath(import.meta.url))},
  server:{path:join(repo,'sandbox/m8-wasm-split/serve_split.py'),sha256:sha(join(repo,'sandbox/m8-wasm-split/serve_split.py')),log:{path:serverLog,sha256:existsSync(serverLog)?sha(serverLog):null}},
  buildCommand,linkFlags,actualLinkCommand,stackOccurrences,defaultStackOccurrences,linkStackPolicyPass};
writeFileSync(receiptPath,JSON.stringify(receipt,null,2)+'\n'); console.log(JSON.stringify(receipt,null,2)); if(!pass)process.exitCode=1;
