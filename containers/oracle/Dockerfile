# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-3.0-or-later

# The official Blender 5.2.0 Linux artifact is x86-64 only.  Pin the
# architecture-specific Ubuntu manifest, not a moving multi-arch tag.
FROM ubuntu:24.04@sha256:019e8eb29a85e74d64925745884f2ec79aa27e3feab36353d24656f4d6b89467

ARG BLENDER_VERSION=5.2.0
ARG BLENDER_COMMIT=fbe6228777e7
ARG BLENDER_ARCHIVE=blender-5.2.0-linux-x64.tar.xz
ARG BLENDER_URL=https://download.blender.org/release/Blender5.2/blender-5.2.0-linux-x64.tar.xz
ARG BLENDER_SHA256=96f6c181a30f4950607839dc84d42a354b250d8a0231b098b59b7bc69c351c48
ARG OIIO_TOOLS_VERSION=2.4.17.0+dfsg-1.1build4

LABEL org.opencontainers.image.title="Pinned Blender 5.2 native oracle" \
      org.opencontainers.image.source="https://github.com/blender/blender" \
      org.opencontainers.image.version="5.2.0-fbe6228777e7" \
      org.opencontainers.image.licenses="GPL-3.0-or-later"

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

# Pin the oiiotool package version.  The base image digest fixes the userspace
# starting point; an unavailable Ubuntu package must fail the build instead of
# silently selecting a newer comparator.
RUN apt-get update \
 && DEBIAN_FRONTEND=noninteractive apt-get install --yes --no-install-recommends \
      ca-certificates \
      curl \
      libegl1 \
      libgl1 \
      libsm6 \
      libxext6 \
      libxfixes3 \
      libxi6 \
      libxkbcommon-x11-0 \
      libxrender1 \
      libxxf86vm1 \
      "openimageio-tools=${OIIO_TOOLS_VERSION}" \
      xz-utils \
 && rm -rf /var/lib/apt/lists/*

# The checksum is published in Blender's official blender-5.2.0.sha256 file.
# Check the bytes before extraction and fail closed on any mismatch.
RUN curl --fail --location --proto '=https' --tlsv1.2 \
      --retry 3 --output "/tmp/${BLENDER_ARCHIVE}" "${BLENDER_URL}" \
 && printf '%s  %s\n' "${BLENDER_SHA256}" "/tmp/${BLENDER_ARCHIVE}" \
      | sha256sum --check --strict - \
 && mkdir --parents /opt/blender \
 && tar --extract --xz --file "/tmp/${BLENDER_ARCHIVE}" \
      --strip-components=1 --directory /opt/blender \
 && rm "/tmp/${BLENDER_ARCHIVE}" \
 && blender_version="$(/opt/blender/blender --version)" \
 && grep --fixed-strings --quiet "Blender ${BLENDER_VERSION}" <<<"${blender_version}" \
 && grep --fixed-strings --quiet "${BLENDER_COMMIT}" <<<"${blender_version}" \
 && oiio_version="$(oiiotool --version)" \
 && grep --fixed-strings --quiet '2.4.17.0' <<<"${oiio_version}" \
 && ln --symbolic /opt/blender/blender /usr/local/bin/blender-oracle

WORKDIR /work
ENTRYPOINT ["/opt/blender/blender"]
CMD ["--background", "--factory-startup"]
