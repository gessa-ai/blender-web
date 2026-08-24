<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M7 Wasm32 write cross-ABI contract

`run.sh` proves that regular Wasm32 saves use Blender's canonical historical
32-bit file layout while the running module retains its real padded wasm32
memory layout.

The contract sends the storage-bearing `m7-type-roundtrip` fixture through
Wasm, unmodified pinned native Blender, and Wasm again with exact semantic state
parity. It separately loads Blender's pinned `BHead4.blend` corpus fixture on
both runtimes, saves it uncompressed with Wasm, independently parses every
BHead4/SDNA structured length, and requires stock-native Blender to read the
result. The binary checks bind `Scene` at 6,664 file bytes versus 6,672 Wasm
memory bytes and reject header, SDNA-size, block-length, DNA1, and truncation
mutations. The upstream global-undo component also exercises three undo pushes,
undo/redo traversal, and ID identity preservation against runtime-layout memfiles.

This is hardware-independent. It creates no browser, WebGPU adapter, split
profile, pixel receipt, result promotion, or milestone promise.
