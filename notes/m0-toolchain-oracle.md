# M0 toolchain, native oracle container, and CI skeleton

Date: 2026-08-11. Scope: the literal M0 reproducibility artifacts that were
absent even though the local M0 harness receipt was green. This note does not
change `GOAL.md`, the protected harness, an oracle pin, or a ledger pass flag.

## Pinned identities

| Component | Immutable identity |
|---|---|
| Blender source and native binary | `blender-v5.2-release` at `fbe6228777e7d9afefcd61a413844e790ae75db7` |
| Official Linux archive | `https://download.blender.org/release/Blender5.2/blender-5.2.0-linux-x64.tar.xz` |
| Archive SHA-256 | `96f6c181a30f4950607839dc84d42a354b250d8a0231b098b59b7bc69c351c48` |
| Ubuntu 24.04 amd64 OCI manifest | `sha256:019e8eb29a85e74d64925745884f2ec79aa27e3feab36353d24656f4d6b89467` |
| Ubuntu `openimageio-tools` | `2.4.17.0+dfsg-1.1build4` (`oiiotool` 2.4.17.0) |

`scripts/m0-oracle-receipt.py` rebuilds/verifies the image, resolves its
immutable repository digest, repeats the Blender commit/default-scene and
`oiiotool` checks against that digest with runtime networking disabled, and
refuses to overwrite its label-bound JSON proof. Host render-comparator
receipts continue to bind their separate `oiiotool` 3.1.16.0 installation.
The wrapper supplies the pinned Blender commit timestamp as
`SOURCE_DATE_EPOCH` and disables BuildKit's timestamped provenance attachment,
so repeated byte-identical builds retain the same image digest.
| emsdk repository | `1ab2e627b1a84567f5284d1baaa5f6be7ccf07de` |
| emsdk release mapping | 6.0.5 -> `dbd755b5da399329c2576f6e3dfa7f419f5d8409` |
| emcc | 6.0.5 at `1db513782be24469589d7cb8a1f1834e9a33f271` |
| emsdk Node | 22.16.0 |

The Blender URL and digest are copied from Blender's official
`blender-5.2.0.sha256` file. The OIIO version is Ubuntu Noble's published
`openimageio` package version. The image build pins the architecture-specific
base manifest and refuses an alternate OIIO package version. It downloads the
Blender archive over HTTPS, verifies SHA-256 before extraction, then requires
both `Blender 5.2.0` and build hash `fbe6228777e7` in `blender --version`.

## Container use

The protected `oracle/` directory remains byte-unchanged. The new reproducible
container lives at `containers/oracle/Dockerfile`, with its wrapper outside the
protected tree:

```sh
bash scripts/oracle-container.sh selfcheck
bash scripts/oracle-container.sh build
bash scripts/oracle-container.sh verify
bash scripts/oracle-container.sh blender --python-expr 'import bpy; print(bpy.app.version_string)'
bash scripts/oracle-container.sh oiiotool --version
```

Runtime networking is disabled and the current directory is the only mounted
project path. The official Blender 5.2.0 Linux archive is x86-64, so the wrapper
always selects `linux/amd64`; Apple Silicon Docker uses its normal amd64
emulation. This container is the headless CPU/state and image-comparator oracle,
not the native Metal UI/render oracle documented by the M4-M6 lanes.

`scripts/m0-selfcheck.py` validates the Dockerfile, wrapper, exact pins, CI
workflow, shell syntax, protected `oracle/PIN`, and the live upstream checkout
identity when that checkout exists. It succeeds without Docker. A real container
execution is a separate, explicit `verify` command.

## CI behavior

`.github/workflows/m0.yml` pins every third-party action to a full commit and
pins both the emsdk repository and SDK release. It runs `reuse lint` before
creating ignored dependency checkouts, restores independent `EM_CACHE` and
ccache directories, then runs a small fail-closed executable subset:

1. validate `oracle/PIN`, emsdk, release-map, and emcc identities;
2. compile and run hello wasm;
3. compile through the `emdawnwebgpu` port;
4. run the compiler through ccache and print its statistics;
5. shallow-fetch the exact Blender commit and verify `FETCH_HEAD`.

This is intentionally a skeleton, not a claim that hosted CI has run. It does
not invoke the milestone harness or write a receipt.

## Why there is no `upstream/PIN`

`upstream/` is an ignored, read-only checkout reconstructed by
`scripts/bootstrap.sh`; `PROVENANCE.md` and `SETUP.md` explicitly prohibit
in-place port files there. Adding `upstream/PIN` would be untracked local state
and would dirty the upstream checkout. The enforceable repository pin therefore
remains the pre-existing protected `oracle/PIN`, while the bootstrap script,
static selfcheck, CI fetch, and live checkout all verify the full commit. The
wording in `GOAL.md` that names `upstream/PIN` is retained unchanged as required.

## Execution status

Static validation passes on the development host. The Docker CLI is installed,
but its daemon is not running, so the 384 MB Blender archive was not downloaded
and the image was not built or executed here. Hosted GitHub Actions also cannot
be claimed until the repository owner publishes the workflow to a remote and a
run completes. Both blockers are environmental; the corresponding commands are
ready and fail closed.
