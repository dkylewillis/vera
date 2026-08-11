# Bundled Tesseract language data

`eng.traineddata` is the official fast English model from
[`tesseract-ocr/tessdata_fast`](https://github.com/tesseract-ocr/tessdata_fast).
It is redistributed under the Apache License 2.0, the same license included at
the repository root.

- Source commit: `87416418657359cb625c412a48b6e1d6d41c29bd`
- SHA-256: `7d4322bd2a7749724879683fc3912cb542f19906c83bcc1a52132556427170b2`
- Size: `4,113,088` bytes

VERA passes this directory directly to PyMuPDF's built-in Tesseract integration,
so English OCR does not require a separate Tesseract installation.
