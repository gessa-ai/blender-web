<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# Canonical source replay audit - 2026-08-20

## Outcome

The exact migration reconstruction path is green and is now explicit in
`patches/canonical`. Starting from Blender `fbe6228777e7`, its single SHA-256-bound squashed
patch applies cleanly and reproduces every final modified or untracked upstream file
byte-for-byte, including file modes and symlink targets. The historical
`PREVIEW_SNAPSHOT.patch` filename is retained because the final-source freezer independently
regenerated `canonical-source.patch` with the same 1,530,148 bytes and SHA-256. The bounded
replayer reports 257 concrete paths; the runbook's older 210 count was the compact `git status`
view in which an untracked directory is one entry.

The numbered `patches/series` history is not clean-replayable and is explicitly retained only
as development audit history. Its first failure is active entry 15,
`0016-gpu-webgpu-texture-format-conversion.patch`, at the GPU CMake source list. This is a
historical overlapping-hunk dependency, not source loss and not a Linux compiler delta.

## Diagnosis

- The series places `0016` before `0019`, but `0016`'s CMake preimage already contains the
  storage, uniform, vertex, and state-table lines introduced by later shared-lane patches.
- Moving `0016` after `0019` cannot resolve the dependency: `0019`'s own CMake preimage
  already contains the texture-format and data-conversion lines introduced by `0016`.
  The two recorded patch preimages are mutually dependent.
- The next shared-lane pair has the same shape: `0016b` expects shader/batch lines from
  `0022`, while `0022` expects the texture line from `0016b`.
- A scratch-only normalization experiment advanced through those pairs and then stopped at
  `0027-ghost-cmake-web.patch` on another stale shared CMake preimage. All experimental
  edits to historical patch payloads were restored byte-for-byte.

The active manifest currently names 125 numbered patches and intentionally retires two
diagnostic-only artifacts (`0117`, `0125`). Those patches mention 116 final path names;
the exact canonical patch contains another 141 paths that were never split into numbered patches.
This matches the migration note's explicit contract: numbered patches are useful history,
while the squashed patch named by `patches/canonical` is the integration-tree authority.

## Evidence and disposition

The stronger `sandbox/final-source-freeze/freeze.py` proof checks the exact pin, pristine real
index, repository state, initialized submodules, complete 20,258-entry live/replay manifests,
patch regeneration, and a final live resnapshot. It passed at
`ledger/buildlogs/20260820T155621-2091828.log`; the normalized receipt is retained at
`sandbox/series-replay/canonical-freeze-receipt.json`. Both manifests are 3,477,328 bytes with
SHA-256 `0d8fcd67732563bee9ed60d6329480408c5654524ba71cbb8c08c6dabec1849a`.

`sandbox/series-replay/verify.py` now treats canonical replay as its default green contract: it
checks the source pin, canonical manifest and digest, source/patch path-set equality, clean
application, modes, symlinks, and final fingerprints. `--numbered-history` remains a diagnostic
mode and still fails honestly at the first stale historical preimage. The two-attempt stop rule
therefore remains binding on piecemeal history repair, while exact source reconstruction is no
longer blocked on it.

## 2026-08-21 integration follow-up

Verified native-platform correction 0149 is now composed into the canonical snapshot. The
source freezer again proves exact clean-pin application, byte-identical 20,258-entry live/replay
manifests, byte-identical patch regeneration, and a stable final resnapshot. The authority remains
the same 257-path squashed patch but is now 1,530,642 bytes with SHA-256
`e03f140fe3f3c6448c9bc7bd52bfa572ea0f774fe5354cd98053341ef8d717b2`; the normalized receipt at
that point replaced the generic receipt path above. The old hash remains valid only for the dated
2026-08-20 evidence and migration save point.

Patch 0150's signed atomic 2D-array spelling correction was subsequently composed by the same
freezer. The authority still spans exactly 257 paths and 20,258 manifest entries; it is now
1,530,681 bytes with SHA-256
`c0b3b32291fd0d680785c53c4f668d7130b90dd6391d726234db1162313a9684`. The current normalized
receipt binds byte-identical live/replay manifests at SHA-256
`ce8b0bc4ae8d9fa253ac3e191b22c989fe24603ba08c7823cd706e2e3f0da3ce`.

Patch 0151's finite-builtin token-boundary correction was then composed without changing the
257-path / 20,258-entry authority. The patch is now 1,531,126 bytes with SHA-256
`22621d7ee011737258e63193a7bfb7c5bd28a81173435e647e4fa2db73eda196`; the current normalized
receipt binds byte-identical live/replay manifests at SHA-256
`1d0c7f68521b25e9b295c7f031ded880d869326d954d8d10aaf830fda23cb903`.

Patch 0152's float3x3 std140 column-packing correction was then composed without changing the
257-path / 20,258-entry authority. The patch is now 1,532,106 bytes with SHA-256
`3045050329c55f3d269c24b8441a209b0e1c0113bf11445d9b45534a4bf1aa71`; the current normalized
receipt binds byte-identical live/replay manifests at SHA-256
`dec961c47e21e5df934641525f20f5ba682ab1bd7075aa705767878d7bf1c21c`.

Patch 0153's native RGB9E5 shared-exponent conversion was then composed without changing the
257-path / 20,258-entry authority. The patch is now 1,535,730 bytes with SHA-256
`a8a582c521d36257d433250b4499e2a65617f16054308d23e2cb048e287f0219`; the current normalized
receipt binds byte-identical live/replay manifests at SHA-256
`3553bf3594cf8f5ebcf0ce4e23ca1dbea4d27376e5f16b817291c8e64bdb3b38`.

Patch 0154's point-list primitive-restart compaction was then composed without changing the
257-path / 20,258-entry authority. The patch is now 1,536,412 bytes with SHA-256
`28dddfc5aaba843c5ce826d4669645f8a79d4dfe2dd911494c9338e3d2d2d659`; the current normalized
receipt binds byte-identical live/replay manifests at SHA-256
`3a2a595ec54ba249861abdccec50ab2b29578fccdd12f9f07aa16fa60bd52489`.

Patch 0155's indexed-strip pipeline-format correction was then composed without changing the
257-path / 20,258-entry authority. The patch is now 1,537,496 bytes with SHA-256
`29c199a2c796b0c3f8d19f03ce7b7d478073a9fd635dd3e833bb3a6bc9bf94ae`; the current normalized
receipt binds byte-identical live/replay manifests at SHA-256
`abf74d3b822383af83655166a12cdc3d58da6f4e771adb96cc66cb0dfc6c7e1a`.

Patch 0156's RG11B10 Vulkan-conversion parity correction was then composed without changing the
257-path / 20,258-entry authority. The patch is now 1,540,303 bytes with SHA-256
`14f8fdbf157aa4216090d19e26956f2aefee5de81ad243f2ff5d938bc42561f4`; the current normalized
receipt binds byte-identical live/replay manifests at SHA-256
`5d3d221838941e8cf8c23bd2500cfc645de41d890a8bccfa3f87b356a60b0169`.

Patch 0157's indexed-subrange binding plan was then composed without changing the 257-path /
20,258-entry authority. The patch is now 1,541,575 bytes with SHA-256
`6473b2a62a450260a41decd73fa200c3831c422763d9f8ac511cc0ad38108e8b`; the current normalized
receipt binds byte-identical live/replay manifests at SHA-256
`695321e772d5440ae3925eaa1cbec5962429649c3128f9aa7aedaeb92663a212`.

Patch 0158's indirect indexed-subrange binding correction was then composed without changing the
257-path / 20,258-entry authority. The patch is now 1,542,075 bytes with SHA-256
`a5ee03e943121c11bb48f4c3e79f83adfc2d7c50974ea6262b56b5924917f3e1`; the current normalized
receipt binds byte-identical live/replay manifests at SHA-256
`4e22dfdd79e6ab956e46d8d51ace0c6fdde8ca7356d88c4a702255f83cf0313b`.

Patch 0159's zero-stride dummy vertex binding was then composed without changing the 257-path /
20,258-entry authority. The patch is now 1,542,552 bytes with SHA-256
`4ea99ca851aa4c0a1fcfefc5fafd4080d30f0998c0d827e555b5a9ac9022acf1`; the current normalized
receipt binds byte-identical live/replay manifests at SHA-256
`b73ea64adf1310f25eefce8cfc04474b35ea99abd460b6b8d012d6aae7d8157c`.

Patch 0160's render-pipeline shader-lifetime identity was then composed without changing the
257-path / 20,258-entry authority. The patch is now 1,544,126 bytes with SHA-256
`ce2a91ec82cf62f5115f2bf20267b4d655abf16a0726335114630195bd838048`; the current normalized
receipt binds byte-identical live/replay manifests at SHA-256
`135586370ee0cff7523b9a6881ce15b4aabea5e4ecaaefddfa767827752713c4`.

Patch 0161's vertex-alias cache-key framing was then composed without changing the 257-path /
20,258-entry authority. The patch is now 1,544,330 bytes with SHA-256
`2b32dfed7921b565c3f17c2e5a32429d724790e4f743681d742134b5d2c9418f`; the current normalized
receipt binds byte-identical live/replay manifests at SHA-256
`79e9e8df23b24e625ae2652ae7449c487726378c4683b347d6a939702fdfeb51`.

Patch 0162's strict WGSL-cache envelope check was then composed without changing the 257-path /
20,258-entry authority. The patch is now 1,544,573 bytes with SHA-256
`2b05464d60d3adde9be154ba4e9051680fdf4c2e81ae052a126bc3016e0f0290`; the current normalized
receipt binds byte-identical live/replay manifests at SHA-256
`09eb8a314d51b4bd66e1ced20e91738738fc9a8da5beba9e065cc2e5b8cf626d`.

Patch 0163's WGSL-cache key binding was then composed without changing the 257-path /
20,258-entry authority. The patch is now 1,545,015 bytes with SHA-256
`e30a29148fcef0487583c97a49322e44fe1e4888845456cd887f97939be9e428`; the current normalized
receipt binds byte-identical live/replay manifests at SHA-256
`17c999a3e9f8e1e5e51446c5dc222781bebf79f98f90da21018086867b2caceb`.

Patch 0164's anisotropic sampler mapping was then composed without changing the 257-path /
20,258-entry authority. The patch is now 1,545,787 bytes with SHA-256
`68c9422ec2204a17348f6a0ab42f0fac3b5eeb012cba9c8eb5d5481b7f937e9d`; the current normalized
receipt binds byte-identical live/replay manifests at SHA-256
`434c9c0e2c0100b54bf19c12b424bf8c96720da958c1bfb9b3e666b10197c81b`.

Patch 0165's feature-aware render-attachment mapping was then composed without changing the
257-path / 20,258-entry authority. The patch is now 1,547,630 bytes with SHA-256
`fe90f9b96bd83c02443b3e154fecc17201f86f96cf0ef1bcaa693330520537b3`; the current normalized
receipt binds byte-identical live/replay manifests at SHA-256
`48bf8892265d0be659778b5fc44d63c3171e7f3956ec10844db24c5c1c506f4c`.

Patch 0166's dummy-attribute default-value correction was then composed without changing the
257-path / 20,258-entry authority. The patch is now 1,548,011 bytes with SHA-256
`31832021c9d755a70e03c7f895ebc77793431fac192de1fde53f56fc43b4c4e5`; the current normalized
receipt binds byte-identical live/replay manifests at SHA-256
`a7af5d5008b634b86bc7eed7182ce78a919d3deb2fdcaa2da3a4e5190bbf3e7e`.

Patch 0167's guarded native `Float32Filterable` request was then composed without changing the
257-path / 20,258-entry authority. The patch is now 1,548,304 bytes with SHA-256
`0b4aa138e5b81f791c4336da87f28343d3609501ec9e872b053aafb7603e2b41`; the current normalized
receipt binds byte-identical live/replay manifests at SHA-256
`780ae03f7f03ac4d45ab0bdd5cef18024e8bd084ad2dd2143e0ec53406e9d4cd`.

Patch 0168's packed strided-upload row-size correction was then composed without changing the
257-path / 20,258-entry authority. The patch is now 1,548,277 bytes with SHA-256
`f7240244a1971f87399010bbf2afe64e145837172cafa67ae9ead6cfa028a5d9`; the current normalized
receipt binds byte-identical live/replay manifests at SHA-256
`a690ef64439b3e8df49b2cf9034e728931481bbb0832825bec4089be797cfe4a`.

Patch 0169's signed packed-normal subrange-update correction was then composed without changing
the 257-path / 20,258-entry authority. The patch is now 1,553,145 bytes with SHA-256
`e6476ec9ed391efbcf3ffcb8281d0497354246f5e2b019bcd144429400b0d76f`; the current normalized
receipt binds byte-identical live/replay manifests at SHA-256
`7633f52f3646196f89530538207cc8b05cea397e6b9f20911f2b65317b46ce9d`.

Patch 0170's BC1/2/3 physical-block upload and faithful feature/type fallback were then composed
without changing the 257-path / 20,258-entry authority. The patch is now 1,560,311 bytes with
SHA-256 `0e920948915c22c2a0cd54d8b483027b4e5dc7ae34f850c7d799fb970cb31336`; the current
normalized receipt binds byte-identical live/replay manifests at SHA-256
`e1e2d5147cc7342708ffc310ae3a1baa1a6ec793d2ebb1633ed28e596f1fed50`.

Patch 0171's sampled-texture component-swizzle mapping and adapter-guarded native feature request
were then composed without changing the 257-path / 20,258-entry authority. The patch is now
1,563,091 bytes with SHA-256
`e8ef2bc5549b8d81b1bb000b54a9ad680714d09c0fe01ee5e217088b46aa6183`; the current normalized
receipt binds byte-identical live/replay manifests at SHA-256
`4a20cb6de8562ef7cca8c67f71254006d9714868ce266b3fa6821339ce727fc1`.

Patch 0172's adapter-guarded native `TextureCompressionBC` request was then composed without
changing the 257-path / 20,258-entry authority. The patch is now 1,563,408 bytes with SHA-256
`c6ec8f525209f0dbc9f193dcdd74a0dd08d5f481e14e0af35ea54e583b9c4047`; the current normalized
receipt binds byte-identical live/replay manifests at SHA-256
`f6293f61eac8dee378f8edb23845201ac2f69bfe95b631b103ef5ea711660bec`.

Patch 0173's fail-closed Unorm16 and D32/S8 creation gates were then composed without changing
the 257-path / 20,258-entry authority. The patch is now 1,564,621 bytes with SHA-256
`cee1d5789abb02fae264161b7a4239231102ac7f798d06354f7b0fab9f9a548d`; the current normalized
receipt binds byte-identical live/replay manifests at SHA-256
`59783c215bac83bb1fc1d45cb06a0919f2e506d965441efdcd205e484ba78a05`.

Patch 0174's fail-closed buffer alignment and range validation was then composed without changing
the 257-path / 20,258-entry authority. The patch is now 1,565,421 bytes with SHA-256
`e4d6d1714e3f270c56ae43f01a2e15b1cc72b09b84d1a88b1a5d6e806883ac6c`; the current normalized
receipt binds byte-identical live/replay manifests at SHA-256
`3a6823e5567cee3f7ac813006ff1da79f08835892bf64242cafe832de094b8f4`.

Patch 0175's fail-closed vertex-to-storage copy validation was then composed without changing the
257-path / 20,258-entry authority. The patch is now 1,566,747 bytes with SHA-256
`1afab3a4d7580eed99f3e116aba85c19329db1e142558130045f1652135a4ece`; the current normalized
receipt binds byte-identical live/replay manifests at SHA-256
`7dd618da9d864ec352165ec5bd1856f99046f7d47e3310c5002b367c734f1f4f`.

Patch 0176's fail-closed buffer allocation-limit validation was then composed without changing
the 257-path / 20,258-entry authority. The patch is now 1,567,504 bytes with SHA-256
`886eea5052e492eac6c0658d44872389fd60bf420e89b3aeab7d61138a3253bf`; the current normalized
receipt binds byte-identical live/replay manifests at SHA-256
`7ff47d3453e57907bf3143f83b08debd324230c6d37f494b81b1cd68c9d82f67`.

Patch 0177's fail-closed texture dimension, array-layer, and mip-limit validation was then
composed without changing the 257-path / 20,258-entry authority. The patch is now 1,569,723
bytes with SHA-256
`42fd53158a55c78a3e8c8ba9a3014dbf505c931302d652620bdee704ab3b15fd`; the current normalized
receipt binds byte-identical live/replay manifests at SHA-256
`6615aed1077016c70a1d0ca0e7bfa3309e48121fdfe47e60cd226be600deca9a`.

Patch 0178's fail-closed uncompressed texture upload-layout validation was then composed without
changing the 257-path / 20,258-entry authority. The patch is now 1,574,038 bytes with SHA-256
`9bdf18537414991749e88d1e86738c234914e19e6f3cbc59cd37fd4c538d9a74`; the current normalized
receipt binds byte-identical live/replay manifests at SHA-256
`2a29bdb087d4792af08819eed932a2c20cae1b821aafda3bed0a56416d46395b`.

Patch 0179's fail-closed texture readback-layout validation was then composed without changing
the 257-path / 20,258-entry authority. The patch is now 1,575,705 bytes with SHA-256
`cd182d11abd926430dae921a21422f191f59e897267ad25d78172de64bb749b0`; the current normalized
receipt binds byte-identical live/replay manifests at SHA-256
`9917405e1a50fc752a0f1e9b21558b83dc53fa28c89679dfd9bc6533e04cfc26`.

Patch 0180's fail-closed non-renderable texture clear-layout validation was then composed without
changing the 257-path / 20,258-entry authority. The patch is now 1,575,846 bytes with SHA-256
`787d9817bf6b6e5c00496fdd720429b592a9af304d286c25d01ecebbc6e97a7d`; the current normalized
receipt binds byte-identical live/replay manifests at SHA-256
`4310652613440ab11c15b38e3507053d56192664073148c67eac4e7f7b22440a`.
