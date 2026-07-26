from __future__ import annotations

import os
import shutil
import socket
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
LAUNCHER = REPO_ROOT / "scripts" / "dev.ps1"
PWSH = shutil.which("pwsh")


def _run_launcher(*arguments: str, environment: dict[str, str]) -> subprocess.CompletedProcess[str]:
    assert PWSH is not None
    return subprocess.run(
        [PWSH, "-NoProfile", "-NonInteractive", "-File", str(LAUNCHER), *arguments],
        cwd=REPO_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )


@pytest.mark.skipif(PWSH is None, reason="PowerShell 7 is required for the Windows launcher")
def test_dev_launcher_rejects_missing_openai_api_key() -> None:
    environment = {
        key: value for key, value in os.environ.items() if key.upper() != "OPENAI_API_KEY"
    }
    environment["OPENAI_BASE_URL"] = "https://example.invalid/v1"

    result = _run_launcher(environment=environment)

    assert result.returncode != 0
    assert "OPENAI_API_KEY" in result.stderr


@pytest.mark.skipif(PWSH is None, reason="PowerShell 7 is required for the Windows launcher")
def test_dev_launcher_rejects_an_explicit_backend_port_that_is_in_use() -> None:
    environment = os.environ.copy()
    environment["OPENAI_API_KEY"] = "test-key"
    environment["OPENAI_BASE_URL"] = "https://example.invalid/v1"

    with socket.create_server(("127.0.0.1", 0)) as listener:
        occupied_port = listener.getsockname()[1]
        result = _run_launcher(
            "-BackendPort",
            str(occupied_port),
            environment=environment,
        )

    assert result.returncode != 0
    assert f"Backend port {occupied_port} is already in use" in result.stderr
