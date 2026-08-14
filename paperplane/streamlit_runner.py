"""Start Streamlit with Paperplane's platform event-loop policy."""

from __future__ import annotations

import asyncio
import sys


def configure_event_loop() -> None:
    """Avoid noisy Proactor connection-reset callbacks on Windows."""
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


def main() -> None:
    configure_event_loop()
    from streamlit.web.cli import main as streamlit_main

    streamlit_main(prog_name="streamlit")


if __name__ == "__main__":
    main()
