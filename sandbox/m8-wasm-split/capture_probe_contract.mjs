// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: GPL-3.0-or-later

export const CORE_MARKER = 'BW_SPLIT_CAPTURE_PROBE_CORE_DISPATCH_V1';
export const CORE_BRANCH = '}else if(cmd=="bwCaptureProbe"){/*' + CORE_MARKER +
  '*/globalThis.__bwCaptureWorkerId=msgData.workerId;' +
  'postMessage({cmd:"bwCaptureProbeAck",token:msgData.token,workerId:msgData.workerId})}else if(cmd==2){';

export function validateCaptureProbeGeneratedSource(source) {
  const count = (needle) => source.split(needle).length - 1;
  const coreBranchCount = count(CORE_BRANCH);
  // The core dispatch itself contains the minified outgoing ACK spelling.
  // Remove that exact independently-validated branch before classifying the
  // post-js worker ACK; a global literal count would conflate the two seams.
  const postJsSource = coreBranchCount === 1 ? source.replace(CORE_BRANCH, '') : source;
  const postJsCount = (needle) => postJsSource.split(needle).length - 1;
  const facts = {
    markerCount: count(CORE_MARKER),
    coreBranchCount,
    postJsHandlerReadableCount: count('if (message?.cmd === "bwCaptureProbe")'),
    postJsHandlerMinifiedCount: count('if(message?.cmd==="bwCaptureProbe")'),
    postJsAckReadableCount: postJsCount('cmd: "bwCaptureProbeAck"'),
    postJsAckMinifiedCount: postJsCount('cmd:"bwCaptureProbeAck"'),
    mainAckListenerReadableCount: count('if (message?.cmd === "bwCaptureProbeAck")'),
    mainAckListenerMinifiedCount: count('if(message?.cmd==="bwCaptureProbeAck")'),
  };
  facts.postJsHandlerCount = facts.postJsHandlerReadableCount + facts.postJsHandlerMinifiedCount;
  facts.postJsAckCount = facts.postJsAckReadableCount + facts.postJsAckMinifiedCount;
  facts.mainAckListenerCount = facts.mainAckListenerReadableCount + facts.mainAckListenerMinifiedCount;
  if (facts.markerCount !== 1 || facts.coreBranchCount !== 1 ||
      facts.postJsHandlerCount !== 1 || facts.postJsAckCount !== 1 ||
      facts.mainAckListenerCount !== 1) {
    throw new Error(`capture probe generated contract failed: ${JSON.stringify(facts)}`);
  }
  return facts;
}
