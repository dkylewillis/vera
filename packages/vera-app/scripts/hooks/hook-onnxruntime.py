"""PyInstaller hook for ONNX Runtime MiniLM inference."""

from PyInstaller.utils.hooks import collect_all, copy_metadata

datas, binaries, hiddenimports = collect_all("onnxruntime")
try:
    extra = collect_all("tokenizers")
    datas += extra[0]
    binaries += extra[1]
    hiddenimports += extra[2]
except Exception:
    hiddenimports.append("tokenizers")
try:
    datas += copy_metadata("onnxruntime")
except Exception:
    pass
try:
    datas += copy_metadata("tokenizers")
except Exception:
    pass
