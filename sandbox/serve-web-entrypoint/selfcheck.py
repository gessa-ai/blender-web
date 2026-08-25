#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-3.0-or-later

"""Hermetic HTTP contract for scripts/serve-web.sh root entry selection."""

from __future__ import annotations

import os
from pathlib import Path
import socket
import subprocess
import tempfile
import time
from urllib.error import URLError
from urllib.request import urlopen


ROOT = Path(__file__).resolve().parents[2]
SERVER = ROOT / "scripts" / "serve-web.sh"


def reserve_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def fetch(port: int, path: str) -> tuple[str, object]:
    with urlopen(f"http://127.0.0.1:{port}{path}", timeout=1) as response:
        return response.read().decode("utf-8"), response.headers


def wait_for_server(port: int, process: subprocess.Popen[str]) -> None:
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        if process.poll() is not None:
            output = process.stdout.read() if process.stdout is not None else ""
            raise AssertionError(f"server exited early ({process.returncode}):\n{output}")
        try:
            fetch(port, "/")
            return
        except (ConnectionError, TimeoutError, URLError):
            time.sleep(0.02)
    raise AssertionError("server did not accept connections within 5 seconds")


def run_server_case(
    shell_files: dict[str, str], expected_root: str, entry: str | None = None
) -> None:
    with tempfile.TemporaryDirectory(prefix="bw-serve-entry-") as temp:
        temp_path = Path(temp)
        shell = temp_path / "shell"
        binary = temp_path / "bin"
        shell.mkdir()
        binary.mkdir()
        for name, contents in shell_files.items():
            (shell / name).write_text(contents, encoding="utf-8")
        (binary / "blender_browser.js").write_text("// fixture\n", encoding="utf-8")

        port = reserve_port()
        env = os.environ.copy()
        env["BLENDER_WEB_SHELL"] = str(shell)
        env["BLENDER_WEB_BIN"] = str(binary)
        if entry is not None:
            env["BLENDER_WEB_ENTRY"] = entry
        process = subprocess.Popen(
            ["bash", str(SERVER), str(port)],
            cwd=ROOT,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        try:
            wait_for_server(port, process)
            root, headers = fetch(port, "/")
            assert root == expected_root
            assert headers["Cross-Origin-Opener-Policy"] == "same-origin"
            assert headers["Cross-Origin-Embedder-Policy"] == "require-corp"
            assert headers["Cross-Origin-Resource-Policy"] == "same-origin"
            assert headers["Cache-Control"] == "no-store"
            for name, contents in shell_files.items():
                explicit, _ = fetch(port, f"/{name}")
                assert explicit == contents
        finally:
            process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=3)


def reject_escaping_entry() -> None:
    with tempfile.TemporaryDirectory(prefix="bw-serve-escape-") as temp:
        temp_path = Path(temp)
        shell = temp_path / "shell"
        binary = temp_path / "bin"
        shell.mkdir()
        binary.mkdir()
        (shell / "index.html").write_text("legacy", encoding="utf-8")
        (temp_path / "outside.html").write_text("outside", encoding="utf-8")
        (binary / "blender_browser.js").write_text("// fixture\n", encoding="utf-8")
        env = os.environ.copy()
        env.update(
            {
                "BLENDER_WEB_SHELL": str(shell),
                "BLENDER_WEB_BIN": str(binary),
                "BLENDER_WEB_ENTRY": "../outside.html",
            }
        )
        result = subprocess.run(
            ["bash", str(SERVER), str(reserve_port())],
            cwd=ROOT,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=3,
            check=False,
        )
        assert result.returncode != 0
        assert "entry escapes shell directory" in result.stdout


def main() -> None:
    both = {"index.html": "legacy-headless", "windowed.html": "windowed-product"}
    run_server_case(both, "windowed-product")
    run_server_case(both, "legacy-headless", entry="index.html")
    run_server_case({"index.html": "custom-index"}, "custom-index")
    reject_escaping_entry()
    print("SERVE_WEB_ENTRYPOINT PASS: 4 cases")


if __name__ == "__main__":
    main()
