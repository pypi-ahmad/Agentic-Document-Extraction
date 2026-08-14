from scripts.handbook_pdf import build_pdf


def test_pdf_build_is_reproducible(tmp_path):
    source = tmp_path / "handbook.md"
    first = tmp_path / "first.pdf"
    second = tmp_path / "second.pdf"
    source.write_text("# Paperplane\n\nA reproducible handbook.\n", encoding="utf-8")

    build_pdf(source, first)
    build_pdf(source, second)

    assert first.read_bytes() == second.read_bytes()
