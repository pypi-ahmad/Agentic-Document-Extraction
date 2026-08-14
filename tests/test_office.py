from pathlib import Path
from subprocess import CompletedProcess

import pytest

from paperplane.ingest import DocumentInputError
from paperplane.office import convert_office_to_pdf


def test_office_conversion_uses_isolated_profile_and_returns_pdf(monkeypatch) -> None:
    captured: list[str] = []
    monkeypatch.setattr("paperplane.office.find_soffice", lambda: Path("soffice.com"))

    def fake_run(command, **kwargs):
        captured.extend(command)
        output_dir = Path(command[command.index("--outdir") + 1])
        output_dir.joinpath("report.pdf").write_bytes(b"%PDF-test")
        assert kwargs["shell"] is False
        return CompletedProcess(command, 0)

    monkeypatch.setattr("paperplane.office.subprocess.run", fake_run)

    result = convert_office_to_pdf(b"office", "report.docx", max_bytes=1_000)

    assert result == b"%PDF-test"
    assert any(value.startswith("-env:UserInstallation=file:") for value in captured)


def test_office_conversion_requires_libreoffice(monkeypatch) -> None:
    monkeypatch.setattr("paperplane.office.find_soffice", lambda: None)

    with pytest.raises(DocumentInputError, match="libreoffice_missing"):
        convert_office_to_pdf(b"office", "report.docx", max_bytes=1_000)
