import asyncio
import sys

import pytest

from paperplane.streamlit_runner import configure_event_loop


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
