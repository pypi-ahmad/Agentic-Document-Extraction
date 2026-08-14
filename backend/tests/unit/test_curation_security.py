import pytest
from pydantic import ValidationError

from app.routers.curation import ExportRequest


@pytest.mark.parametrize("name", ["report\r\nX-Injected: yes", 'report".zip', "report\\name"])
def test_export_name_rejects_header_unsafe_characters(name: str) -> None:
    with pytest.raises(ValidationError):
        ExportRequest(name=name, document_ids=["document-id"])


def test_export_name_accepts_normal_human_name() -> None:
    request = ExportRequest(name="August invoices", document_ids=["document-id"])

    assert request.name == "August invoices"
