from vera_ingest.formats import source_mime_type


def test_source_mime_type_covers_pdf_markdown_office_html():
    assert source_mime_type("manual.pdf") == "application/pdf"
    assert source_mime_type("notes.md") == "text/markdown"
    assert source_mime_type("notes.markdown") == "text/markdown"
    assert (
        source_mime_type("memo.docx")
        == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
    assert (
        source_mime_type("slides.pptx")
        == "application/vnd.openxmlformats-officedocument.presentationml.presentation"
    )
    assert (
        source_mime_type("budget.xlsx")
        == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    assert source_mime_type("page.html") == "text/html"
    assert source_mime_type("page.htm") == "text/html"
