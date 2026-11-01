# vera-ingest-ooxml

Lightweight ingest pipeline for Word (`.docx`), PowerPoint (`.pptx`), and Excel
(`.xlsx`). It uses `python-docx`, `python-pptx`, and `openpyxl`, with no
Torch or layout models.

The provider name is `ooxml`. It is the default parser for those extensions.
Docling remains available with `--parser docling` when a higher-fidelity
layout parse is worth the extra install.
