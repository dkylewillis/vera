"""PyInstaller hook for the bundled Sentence Transformers embedder."""

from PyInstaller.utils.hooks import collect_all, copy_metadata

datas, binaries, hiddenimports = collect_all("sentence_transformers")
try:
    datas += copy_metadata("sentence-transformers")
except Exception:
    pass
