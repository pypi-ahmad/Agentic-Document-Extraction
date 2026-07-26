import json
from pathlib import Path

import pytest

from app.services.parsing.paddleocr_docker import (
    PaddleOCRVLDockerRunner,
    _load_regions,
)
from app.services.parsing.paddleocr_vl import PaddleOCRVLResponseError


def _runner(tmp_path: Path) -> PaddleOCRVLDockerRunner:
    worker = tmp_path / "worker.py"
    worker.write_text("pass", "utf-8")
    return PaddleOCRVLDockerRunner(
        image="registry/paddle@sha256:" + "a" * 64,
        cache_dir=tmp_path / "cache",
        timeout_seconds=30,
        worker_script=worker,
    )


def test_docker_command_is_job_scoped_and_has_no_ports(tmp_path: Path) -> None:
    runner = _runner(tmp_path)
    pages = tmp_path / "work" / "pages"
    output = tmp_path / "work" / "paddleocr-vl"
    pages.mkdir(parents=True)
    output.mkdir()

    command = runner._docker_command(
        job_id="a" * 32,
        container_name="ade-paddle-" + "a" * 32,
        pages_dir=pages,
        output_dir=output,
    )

    assert command[:3] == ["docker", "run", "--rm"]
    assert "ai.paperplane.job=" + "a" * 32 in command
    assert "--gpus" in command
    assert "--publish" not in command
    assert "--cap-drop" in command
    assert runner.image in command
    assert any(item.endswith("target=/home/paddleocr/.paddlex") for item in command)


def test_default_worker_script_resolves_from_repository_root(tmp_path: Path) -> None:
    runner = PaddleOCRVLDockerRunner(
        image="registry/paddle@sha256:" + "a" * 64,
        cache_dir=tmp_path / "cache",
        timeout_seconds=30,
    )

    assert runner.worker_script == (
        Path(__file__).resolve().parents[3] / "deploy" / "paddleocr-vl" / "worker.py"
    )


def test_result_normalizes_reading_order_and_table_metadata(tmp_path: Path) -> None:
    result = tmp_path / "result.json"
    result.write_text(
        json.dumps(
            {
                "pages": [
                    {
                        "page_number": 1,
                        "width": 1000,
                        "height": 2000,
                        "parsing_res_list": [
                            {
                                "block_id": 9,
                                "block_order": 2,
                                "block_label": "table",
                                "block_bbox": [100, 200, 900, 800],
                                "block_content": "| A |",
                                "table_refinement": {
                                    "pred_html": "<table><tr><td>A</td></tr></table>",
                                    "cell_box_list": [[0, 0, 10, 10]],
                                },
                            }
                        ],
                    }
                ]
            }
        ),
        "utf-8",
    )

    pages = _load_regions(result, [1])

    assert pages[1][0].type == "table"
    assert pages[1][0].order == 2
    assert pages[1][0].bbox.left == 0.1
    assert pages[1][0].table_html == "<table><tr><td>A</td></tr></table>"
    assert pages[1][0].table_cells[0].text == "A"


def test_result_rejects_missing_pages(tmp_path: Path) -> None:
    result = tmp_path / "result.json"
    result.write_text('{"pages": []}', "utf-8")

    with pytest.raises(PaddleOCRVLResponseError, match="every requested page"):
        _load_regions(result, [1])
