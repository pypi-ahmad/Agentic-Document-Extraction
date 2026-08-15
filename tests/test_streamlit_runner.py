import asyncio
import sys

import pytest

from paperplane.streamlit_runner import (
    configure_event_loop,
    isolate_external_cuda_toolkit,
    validate_torch_runtime,
)


def test_isolate_external_cuda_toolkit_removes_only_toolkit_paths(monkeypatch) -> None:
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setenv(
        "PATH",
        ";".join(
            [
                r"C:\Windows\System32",
                r"C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v13.3\bin",
                r"D:\tools",
            ]
        ),
    )

    isolate_external_cuda_toolkit()

    assert sys.platform == "win32"
    assert __import__("os").environ["PATH"] == r"C:\Windows\System32;D:\tools"


def test_validate_torch_runtime_rejects_missing_record(monkeypatch) -> None:
    class IncompleteDistribution:
        @staticmethod
        def read_text(_filename):
            return None

    monkeypatch.setattr(
        "paperplane.streamlit_runner.importlib.metadata.distribution",
        lambda _name: IncompleteDistribution(),
    )

    with pytest.raises(RuntimeError, match="RECORD is missing"):
        validate_torch_runtime()


def test_configure_event_loop_is_a_noop_outside_windows() -> None:
    if sys.platform == "win32":
        pytest.skip("Non-Windows policy contract")
    policy = asyncio.get_event_loop_policy()

    configure_event_loop()

    assert asyncio.get_event_loop_policy() is policy


@pytest.mark.skipif(sys.platform != "win32", reason="Windows event-loop policy")
def test_configure_event_loop_uses_selector_on_windows() -> None:
    previous = asyncio.get_event_loop_policy()
    try:
        configure_event_loop()
        loop = asyncio.new_event_loop()
        try:
            assert isinstance(loop, asyncio.SelectorEventLoop)
        finally:
            loop.close()
    finally:
        asyncio.set_event_loop_policy(previous)
