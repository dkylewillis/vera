"""PyInstaller hook for the first-class Docling ingest pipeline."""

from PyInstaller.utils.hooks import collect_data_files, collect_submodules, copy_metadata

hiddenimports = collect_submodules("vera_ingest_docling")
datas = collect_data_files("vera_ingest_docling")
try:
    datas += copy_metadata("vera-ingest-docling")
except Exception:
    pass
