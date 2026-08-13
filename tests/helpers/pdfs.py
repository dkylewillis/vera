"""PDF factories shared across conversion, search, and sidecar tests."""

from __future__ import annotations

from pathlib import Path


def make_pdf(path: Path) -> Path:
    import fitz

    doc = fitz.open()
    page = doc.new_page()
    page.insert_text(
        (72, 72), "Chapter 110 Zoning\nRestaurants require one parking space per 100 square feet."
    )
    page2 = doc.new_page()
    page2.insert_text(
        (72, 72), "Stormwater Manual\nDetention is required when impervious area increases."
    )
    doc.save(path)
    doc.close()
    return path


def make_topic_pdf(path: Path, heading: str, body: str) -> Path:
    import fitz

    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), heading, fontsize=20)
    page.insert_text((72, 110), body, fontsize=11)
    doc.save(path)
    doc.close()
    return path


def make_structured_pdf(path: Path, with_image: bool = True) -> Path:
    """PDF with sized headings, body text, and an optional embedded image."""
    import fitz

    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Chapter 110 Zoning", fontsize=20)
    page.insert_text((72, 110), "Article 5 Parking", fontsize=16)
    page.insert_text(
        (72, 140),
        "Restaurants require one parking space per 100 square feet of floor area.",
        fontsize=11,
    )
    if with_image:
        pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 40, 40))
        pix.clear_with(128)
        page.insert_image(fitz.Rect(72, 200, 172, 300), pixmap=pix)
    page2 = doc.new_page()
    page2.insert_text((72, 72), "Chapter 200 Stormwater", fontsize=20)
    page2.insert_text(
        (72, 110),
        "Detention is required when impervious area increases beyond limits.",
        fontsize=11,
    )
    doc.save(path)
    doc.close()
    return path
