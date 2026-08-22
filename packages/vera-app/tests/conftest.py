import pytest


@pytest.fixture(autouse=True)
def sidecar_tokenizer_env(monkeypatch):
    """Keep Hugging Face tokenizers single-threaded in sidecar tests."""
    monkeypatch.setenv("TOKENIZERS_PARALLELISM", "false")
