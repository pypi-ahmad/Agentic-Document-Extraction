"""Start Streamlit with Paperplane's platform event-loop policy."""

from __future__ import annotations

import asyncio
import importlib.metadata
import os
import sys


def isolate_external_cuda_toolkit() -> None:
    """Keep Windows from mixing system CUDA DLLs with PyTorch's bundled runtime."""

    if sys.platform != "win32":
        return
    os.environ["PATH"] = ";".join(
        entry
        for entry in os.environ.get("PATH", "").split(";")
        if "nvidia gpu computing toolkit\\cuda" not in entry.casefold()
    )


def validate_torch_runtime() -> None:
    """Reject incomplete Torch metadata and incompatible bundled CUDA libraries."""

    isolate_external_cuda_toolkit()
    distribution = importlib.metadata.distribution("torch")
    if not distribution.read_text("RECORD"):
        raise RuntimeError("Torch installation metadata is incomplete: RECORD is missing")

    import torch

    if torch.cuda.is_available():
        sample = torch.randn(1, 1, 8, 8, device="cuda")
        convolution = torch.nn.Conv2d(1, 1, 3, padding=1).cuda()
        convolution(sample)
        torch.cuda.synchronize()


def configure_event_loop() -> None:
    """Avoid noisy Proactor connection-reset callbacks on Windows."""
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


def main() -> None:
    isolate_external_cuda_toolkit()
    configure_event_loop()
    from streamlit.web.cli import main as streamlit_main

    streamlit_main(prog_name="streamlit")


if __name__ == "__main__":
    main()
