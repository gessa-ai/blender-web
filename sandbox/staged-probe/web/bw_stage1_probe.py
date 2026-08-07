# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: CC0-1.0
# Synthetic module ABSENT from blender_browser.data. Fetched over the wire
# post-boot and mounted into WASMFS to prove staged/lazy loading works.
MARKER = "STAGE1_LAZY_OK_44424edfbc32"
def hello():
    return MARKER
