<!--
SPDX-FileCopyrightText: 2026 blender-web contributors
SPDX-License-Identifier: CC0-1.0
-->

# WSL2 hardware-WebGPU deferral contract

This device-free contract verifies that each hardware-dependent M3-M8 portion is
recorded in `ledger/deferred.json` with the exact externally proven WSL2 blocker.
It scopes that blocker to this host, requires the real driver-operated Apple M4 Pro
revisit path, and rejects the falsified Windows-reboot route. Cycles-CPU remains
27/27 receipt-backed, and M8's separate size/latency failure remains active.

Run through the repository build-output wrapper:

```sh
harness/buildwrap.sh .host-tools/bin/python3.13 sandbox/s7-deferral-contract/verify.py
```
