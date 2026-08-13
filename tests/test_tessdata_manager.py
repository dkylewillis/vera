"""Unit tests for on-demand Tesseract language-pack resolution and download."""

from __future__ import annotations

import hashlib
import io

import pytest

from vera_ingest_pymupdf import tessdata_manager as tdm


def _fake_response(data: bytes, *, content_length: int | None = None):
    class _FakeResponse(io.BytesIO):
        headers = {}

        def __enter__(self):
            return self

        def __exit__(self, *exc_info):
            return False

    response = _FakeResponse(data)
    response.headers = {"Content-Length": str(content_length if content_length is not None else len(data))}
    return response


def test_is_bundled_and_is_known():
    assert tdm.is_bundled("eng")
    assert not tdm.is_bundled("fra")
    assert tdm.is_known("eng")
    assert tdm.is_known("fra")  # in the curated download registry
    assert not tdm.is_known("zzz")


def test_is_bundled_rejects_path_traversal_codes():
    assert tdm.is_bundled("../tessdata/eng") is False
    assert tdm.is_bundled("..\\tessdata\\eng") is False
    assert tdm.is_bundled("eng/../eng") is False
    assert tdm.is_bundled("eng/foo") is False
    assert tdm.is_known("../tessdata/eng") is False
    assert tdm.is_valid_language_code("../tessdata/eng") is False
    assert tdm.is_valid_language_code("chi_sim") is True


def test_ensure_language_data_rejects_path_like_codes(tmp_path):
    with pytest.raises(ValueError, match="Invalid OCR language"):
        tdm.ensure_language_data("../tessdata/eng", allow_download=False, cache_dir=tmp_path)
    with pytest.raises(ValueError, match="Invalid OCR language"):
        tdm.ensure_language_data("eng+../tessdata/eng", allow_download=True, cache_dir=tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_known_language_codes_includes_bundled_and_registry():
    codes = tdm.known_language_codes()
    assert "eng" in codes
    assert "fra" in codes
    assert codes == sorted(codes)


def test_language_choice_labels_puts_english_first_with_tesseract_codes():
    labels = tdm.language_choice_labels()
    assert labels[0] == ("eng", "English (eng)")
    by_code = dict(labels)
    assert by_code["spa"] == "Spanish (spa)"
    assert by_code["chi_sim"] == "Chinese (Simplified) (chi_sim)"
    names_after_eng = [label for code, label in labels if code != "eng"]
    assert names_after_eng == sorted(names_after_eng, key=str.casefold)


def test_default_cache_dir_respects_env_override(monkeypatch, tmp_path):
    monkeypatch.setenv("VERA_TESSDATA_CACHE", str(tmp_path / "custom-cache"))
    assert tdm.default_cache_dir() == tmp_path / "custom-cache"


def test_describe_language_codes_reports_bundled_and_unknown(tmp_path, monkeypatch):
    monkeypatch.setenv("VERA_TESSDATA_CACHE", str(tmp_path))
    entries = {entry["code"]: entry for entry in tdm.describe_language_codes("eng+fra+zzz")}
    assert entries["eng"]["bundled"] is True
    assert entries["eng"]["downloadable"] is True
    assert entries["eng"]["cached"] is True
    assert entries["fra"]["bundled"] is False
    assert entries["fra"]["downloadable"] is True
    assert entries["fra"]["cached"] is False
    assert entries["fra"]["size_bytes"] == tdm.KNOWN_LANGUAGES["fra"].size
    assert entries["zzz"]["downloadable"] is False
    assert entries["zzz"]["cached"] is False


def test_ensure_language_data_bundled_english_needs_no_cache_dir(tmp_path):
    resolved = tdm.ensure_language_data("eng", allow_download=False, cache_dir=tmp_path / "unused")
    assert resolved is not None
    assert not (tmp_path / "unused").exists()  # bundled path never touches the cache dir


def test_ensure_language_data_missing_without_download_returns_none(tmp_path):
    resolved = tdm.ensure_language_data("fra", allow_download=False, cache_dir=tmp_path)
    assert resolved is None
    assert not (tmp_path / "fra.traineddata").exists()


def test_ensure_language_data_unknown_code_without_download_returns_none(tmp_path):
    resolved = tdm.ensure_language_data("zzz", allow_download=False, cache_dir=tmp_path)
    assert resolved is None


def test_ensure_language_data_unknown_code_with_download_raises(tmp_path):
    with pytest.raises(tdm.UnknownOCRLanguageError):
        tdm.ensure_language_data("zzz", allow_download=True, cache_dir=tmp_path)


def test_ensure_language_data_downloads_and_verifies_checksum(tmp_path, monkeypatch):
    payload = b"fake-traineddata-bytes"
    digest = hashlib.sha256(payload).hexdigest()
    monkeypatch.setitem(tdm.KNOWN_LANGUAGES, "tst", tdm.LanguagePackInfo("Test", digest, len(payload)))
    monkeypatch.setattr(tdm.urllib.request, "urlopen", lambda *a, **k: _fake_response(payload))

    progress_calls = []
    resolved = tdm.ensure_language_data(
        "tst",
        allow_download=True,
        cache_dir=tmp_path,
        progress=lambda code, downloaded, total: progress_calls.append((code, downloaded, total)),
    )

    assert resolved == str(tmp_path)
    assert (tmp_path / "tst.traineddata").read_bytes() == payload
    assert progress_calls and progress_calls[-1][0] == "tst"
    assert progress_calls[-1][1] == len(payload)


def test_ensure_language_data_rejects_checksum_mismatch(tmp_path, monkeypatch):
    payload = b"unexpected-bytes"
    monkeypatch.setitem(
        tdm.KNOWN_LANGUAGES, "tst", tdm.LanguagePackInfo("Test", "0" * 64, len(payload))
    )
    monkeypatch.setattr(tdm.urllib.request, "urlopen", lambda *a, **k: _fake_response(payload))

    with pytest.raises(tdm.OCRLanguageDownloadError, match="integrity"):
        tdm.ensure_language_data("tst", allow_download=True, cache_dir=tmp_path)
    assert not (tmp_path / "tst.traineddata").exists()


def test_ensure_language_data_reuses_valid_cache_without_downloading(tmp_path, monkeypatch):
    payload = b"cached-traineddata-bytes"
    digest = hashlib.sha256(payload).hexdigest()
    monkeypatch.setitem(tdm.KNOWN_LANGUAGES, "tst", tdm.LanguagePackInfo("Test", digest, len(payload)))
    (tmp_path / "tst.traineddata").write_bytes(payload)

    def _boom(*_args, **_kwargs):
        raise AssertionError("should not re-download an already-cached, valid file")

    monkeypatch.setattr(tdm.urllib.request, "urlopen", _boom)
    resolved = tdm.ensure_language_data("tst", allow_download=True, cache_dir=tmp_path)
    assert resolved == str(tmp_path)


def test_ensure_language_data_does_not_trust_size_only_cache(tmp_path, monkeypatch):
    payload = b"cached-traineddata-bytes"
    digest = hashlib.sha256(payload).hexdigest()
    monkeypatch.setitem(tdm.KNOWN_LANGUAGES, "tst", tdm.LanguagePackInfo("Test", digest, len(payload)))
    (tmp_path / "tst.traineddata").write_bytes(b"0" * len(payload))
    downloaded = []

    def _fake_urlopen(*_args, **_kwargs):
        downloaded.append(True)
        return _fake_response(payload)

    monkeypatch.setattr(tdm.urllib.request, "urlopen", _fake_urlopen)
    resolved = tdm.ensure_language_data("tst", allow_download=True, cache_dir=tmp_path)
    assert resolved == str(tmp_path)
    assert downloaded
    assert (tmp_path / "tst.traineddata").read_bytes() == payload


def test_ensure_language_data_mixed_bundled_and_downloadable_copies_bundled_into_cache(
    tmp_path, monkeypatch
):
    payload = b"fake-french-traineddata"
    digest = hashlib.sha256(payload).hexdigest()
    monkeypatch.setitem(tdm.KNOWN_LANGUAGES, "fra", tdm.LanguagePackInfo("French", digest, len(payload)))
    monkeypatch.setattr(tdm.urllib.request, "urlopen", lambda *a, **k: _fake_response(payload))

    resolved = tdm.ensure_language_data("eng+fra", allow_download=True, cache_dir=tmp_path)

    assert resolved == str(tmp_path)
    assert (tmp_path / "eng.traineddata").is_file()
    assert (tmp_path / "fra.traineddata").read_bytes() == payload


def test_ensure_language_data_mixed_bundled_without_download_assembles_cache(tmp_path, monkeypatch):
    payload = b"cached-spanish-traineddata"
    digest = hashlib.sha256(payload).hexdigest()
    monkeypatch.setitem(tdm.KNOWN_LANGUAGES, "spa", tdm.LanguagePackInfo("Spanish", digest, len(payload)))
    (tmp_path / "spa.traineddata").write_bytes(payload)

    resolved = tdm.ensure_language_data("eng+spa", allow_download=False, cache_dir=tmp_path)

    assert resolved == str(tmp_path)
    assert (tmp_path / "eng.traineddata").is_file()
    assert (tmp_path / "spa.traineddata").read_bytes() == payload


def test_download_aborts_when_stream_exceeds_pinned_size(tmp_path, monkeypatch):
    payload = b"too-long-payload"
    monkeypatch.setitem(tdm.KNOWN_LANGUAGES, "tst", tdm.LanguagePackInfo("Test", "0" * 64, 4))
    monkeypatch.setattr(tdm.urllib.request, "urlopen", lambda *_a, **_k: _fake_response(payload))

    with pytest.raises(tdm.OCRLanguageDownloadError, match="exceeded"):
        tdm.ensure_language_data("tst", allow_download=True, cache_dir=tmp_path)
    assert not (tmp_path / "tst.traineddata").exists()


def test_download_ocr_language_data_public_helper(tmp_path, monkeypatch):
    payload = b"fake-bytes"
    digest = hashlib.sha256(payload).hexdigest()
    monkeypatch.setitem(tdm.KNOWN_LANGUAGES, "tst", tdm.LanguagePackInfo("Test", digest, len(payload)))
    monkeypatch.setattr(tdm.urllib.request, "urlopen", lambda *a, **k: _fake_response(payload))

    resolved = tdm.download_ocr_language_data("tst", cache_dir=tmp_path)
    assert resolved == str(tmp_path)
    assert (tmp_path / "tst.traineddata").read_bytes() == payload
