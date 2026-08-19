// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: GPL-3.0-or-later

let installedModule = null;
let installedInstance = null;
let instanceCount = 0;

self.onmessage = (event) => {
  const message = event.data;
  if (!message || message.command !== 'install') {
    self.postMessage({ command: 'error', error: 'unknown worker command' });
    return;
  }
  try {
    if (!(message.module instanceof WebAssembly.Module)) {
      throw new Error('structured clone is not a WebAssembly.Module');
    }
    if (installedInstance === null) {
      installedModule = message.module;
      installedInstance = new WebAssembly.Instance(installedModule, {});
      instanceCount++;
    }
    self.postMessage({
      command: 'ready',
      generation: message.generation,
      instanceCount,
      value: installedInstance.exports.value(),
    });
  }
  catch (error) {
    self.postMessage({ command: 'error', error: String(error && error.stack || error) });
  }
};
