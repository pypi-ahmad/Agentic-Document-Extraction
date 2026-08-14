import fitz

from paperplane.pdf_inspector_parser import parse_pdf_with_inspector


def _pdf() -> bytes:
    document = fitz.open()
    for page_number in range(1, 3):
        page = document.new_page(width=300, height=400)
        page.insert_text((30, 50), f"Heading page {page_number}", fontsize=16)
        page.insert_text((30, 90), f"Body content {page_number}", fontsize=10)
    value = document.tobytes()
    document.close()
    return value


def test_pdf_inspector_adapter_preserves_selected_page_and_grounding() -> None:
    result = parse_pdf_with_inspector(_pdf(), (2,))

    assert result.pdf_type == "text_based"
    assert 0 <= result.confidence <= 1
    assert list(result.pages) == [2]
    page = result.pages[2]
    assert page.parser == "pdf_inspector"
    assert "Heading page 2" in page.blocks[0].markdown
    assert page.blocks[0].atomic_lines
    assert page.blocks[0].atomic_lines[0].box.top < 0.2
