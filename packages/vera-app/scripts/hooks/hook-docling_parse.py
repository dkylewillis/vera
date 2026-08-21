"""PyInstaller hook: docling-parse needs pdf_resources next to the native .pyd."""

from PyInstaller.utils.hooks import collect_all

datas, binaries, hiddenimports = collect_all("docling_parse")
