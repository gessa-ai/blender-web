# r58 toolbar premise correction: triangle-fan fix already closed the queue item

Status: diagnosis complete. The toolbar queue item is **CLOSED by fd624eb / patch 0134**. No new source patch, comparator change, golden change, or threshold change is warranted.

## Result

The previously reported left-toolbar glyph and anti-aliasing seam is not present in the current D-9 capture. At the established max-channel absolute threshold greater than 0.016, the 1280x720 DPR1 current capture has:

- 2 failing pixels in the entire toolbar rectangle, both isolated one-pixel components at `(13,84)` and `(32,646)`.
- 1 failing pixel in the icon strip.
- 0 failing pixels in the x48 through x63 seam strip. Its maximum difference is 0.015686275, below threshold.

Before patch 0134, the same regions had 1,022 toolbar failures, 995 icon-strip failures, and 32 seam failures. The old r39 overlap/SDF premise is therefore falsified. The visible damage was missing diagonal halves of textured icon quads, not an SDF edge, blending fringe, overlap-region load, scissor, or coordinate offset.

The licensed contact sheet is `sandbox/gpu-toolbar-0134/toolbar-0134-premise-correction-contact.png`. It shows the native oracle, pre-0134 web capture, amplified pre-0134 difference, current D-9 web capture, and amplified current difference in that order.

## Native-faithful cause and already-landed fix

The toolbar icon path is:

1. `interface_icons.cc:1408-1476`, where `icon_draw_rect` uses `PixelBitmapDrawer`.
2. `glutil.cc:45-118`, where `PixelBitmapDrawer::draw` emits four vertices with `immBegin(GPU_PRIM_TRI_FAN, 4)` at lines 99-111.
3. Before 0134, the WebGPU backend treated that fan as a triangle strip. A four-vertex fan and strip use different second triangles, which explains the diagonally truncated bitmap quads in r39 and the pre-0134 1280 capture.

Commit `fd624eb14cdd0b0788920a096d2b623df47ce7f2`, patch `patches/0134-gpu-webgpu-triangle-fan-emulation.patch`, already implements the minimal native-faithful repair:

- `wgpu_immediate.cc:79-109` expands a fan into exact `(0,i,i+1)` triangle-list indices.
- `wgpu_immediate.cc:194-200` binds that index buffer and issues `DrawIndexed`.
- `wgpu_pipeline.cc:44-48` makes any unhandled raw fan path visible instead of silently mapping it to a strip.
- Native Metal uses the same fan-to-triangle-list construction at `mtl_immediate.mm:198-232`.

Patch disposition: no new patch number is reserved and no source fence is proposed. Patch 0134 is the fix. Any future regression-only work should remain in a test or evidence fence and must not change Blender-visible behavior.

## Controls that falsify the earlier alternatives

### r28b load/store A/B

The retained r28b baseline and forced-always-load captures are byte-identical in all three measured areas:

- toolbar: 0 changed pixels, maximum difference 0
- icon strip: 0 changed pixels, maximum difference 0
- seam: 0 changed pixels, maximum difference 0

Thus the r28b load/store experiment had zero effect on the toolbar corruption. Region overlap/load behavior was not its cause.

### Coordinate shift

The exact 0/0 alignment is decisively best. Current icon-strip comparison is 1 failing pixel at 0/0. Shifting the web crop by one pixel in either x direction produces 3,146 failures; shifting by one pixel in y produces 3,984 or 4,015. The pre-0134 capture also scores best at 0/0. This rules out a one-pixel coordinate or scissor displacement.

## Reclassification of the current D-9 mass

The current whole-window count is 4,653 pixels. The disjoint partition is:

| Region | Failing pixels | Interpretation |
|---|---:|---|
| Toolbar | 2 | Closed, two singleton residuals |
| Viewport | 1,784 | Existing D-9 viewport residue, outside this diagnosis |
| Right rail | 192 | Existing D-9 right-rail residue, outside this diagnosis |
| Bottom | 2,675 | Capture-state mismatch described below |
| Top bar | 0 | No threshold failures |

The bottom mass is not toolbar or glyph anti-aliasing:

- 2,187 pixels form one connected component with bounding box `(2,650)-(1049,696)`, the one-pixel Timeline editor perimeter. Its two dominant exact color transitions are native `(58,58,58)` to web `(76,76,76)` for 1,056 pixels and native `(46,46,46)` to web `(65,65,65)` for 1,031 pixels.
- The other 488 pixels form 11 components within `(6,701)-(108,716)`. They spell the web-only `Pan` and `Options` status hints that are absent from the native golden.

The source trace explains both observations:

- `wm_draw.cc:1191-1199` calls `ED_screen_draw_edges` after composing area regions.
- `screen_draw.cc:128-155` chooses the active area from `screen->active_region` or `win->runtime->eventstate->xy`.
- `screen_draw.cc:202-219` draws `TH_EDITOR_OUTLINE` or `TH_EDITOR_OUTLINE_ACTIVE` according to that active-area choice.
- `sandbox/m4-d9-gate/capture_m4.mjs:174-176` deliberately moves the browser mouse to canvas `(12,height-12)` and then `(16,height-16)`, which is the bottom-left Timeline/status area after Blender's event-coordinate conversion.
- The native golden capture does not inject that browser event. Consequently, the two captures do not share active-area or status-hint state.

This is a measurement-state issue, not evidence for another WebGPU rendering fix. It is recorded here without opening a fix and without changing the comparator, golden, or acceptance threshold. Any later gate cleanup must make native and web pointer/event state identical.

## Reproduction and evidence

Run from the repository root:

```sh
python3 sandbox/gpu-toolbar-0134/analyze_toolbar.py > sandbox/gpu-toolbar-0134/metrics.txt
```

The script records its exact source paths, SHA-256 hashes, rectangles, threshold, connected components, coordinate controls, r28b A/B result, D-9 partition, and bottom-perimeter color pairs. `analysis-command.txt` is the command receipt. The three 72x404 crops use the shared native/pre/current rectangle x0 through x71 and y52 through y455. `current-bottom-residual-contact.png` is the licensed native/current/amplified-difference proof for y649 through y719.

No browser or rebuild is required for this diagnosis. If a future capture regression check is added, its acceptance should preserve the current facts: current toolbar no more than 2 threshold failures, icon strip no more than 1, seam 0, 0/0 alignment strictly best, and r28b A/B zero effect. It must not hide regressions by changing thresholds or goldens.
