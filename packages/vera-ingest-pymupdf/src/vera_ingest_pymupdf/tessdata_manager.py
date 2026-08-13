"""Resolve, cache, and optionally download Tesseract ``.traineddata`` language data.

VERA bundles the English (``eng``) fast model so default PyMuPDF OCR works
offline with no setup (see ``tessdata/README.md``). Every other language
listed in :data:`KNOWN_LANGUAGES` below is *not* bundled, but VERA can fetch
it on demand from the same upstream source (pinned by commit and verified by
SHA-256, exactly like the bundled English model) into a per-user cache
directory. Downloading is always opt-in via ``allow_download`` — nothing in
this module performs network I/O unless a caller explicitly asks for it.

Language codes outside :data:`KNOWN_LANGUAGES` are not auto-downloadable;
callers must install a ``.traineddata`` file manually and set
``TESSDATA_PREFIX`` (unchanged from VERA's original behavior).
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import tempfile
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import NamedTuple

__all__ = [
    "KNOWN_LANGUAGES",
    "TESSDATA_FAST_COMMIT",
    "LanguagePackInfo",
    "OCRLanguageDownloadError",
    "ProgressCallback",
    "UnknownOCRLanguageError",
    "default_cache_dir",
    "default_ocr_language_cache_dir",
    "describe_language_codes",
    "describe_ocr_languages",
    "download_ocr_language_data",
    "ensure_language_data",
    "is_bundled",
    "is_known",
    "is_valid_language_code",
    "known_language_codes",
    "language_choice_labels",
    "validate_ocr_language",
]

# Commit pinned in `tesseract-ocr/tessdata_fast` that both the bundled `eng`
# model (see tessdata/README.md) and every entry below were fetched from.
TESSDATA_FAST_COMMIT = "87416418657359cb625c412a48b6e1d6d41c29bd"
_TESSDATA_FAST_BASE_URL = (
    f"https://raw.githubusercontent.com/tesseract-ocr/tessdata_fast/{TESSDATA_FAST_COMMIT}"
)
_BUNDLED_DIR = Path(__file__).resolve().parent / "tessdata"
_DOWNLOAD_CHUNK_SIZE = 256 * 1024


class LanguagePackInfo(NamedTuple):
    """Pinned integrity metadata for one downloadable ``.traineddata`` file."""

    name: str
    sha256: str
    size: int


class UnknownOCRLanguageError(ValueError):
    """Raised when an OCR language code is neither bundled nor downloadable."""


class OCRLanguageDownloadError(RuntimeError):
    """Raised when fetching or verifying a language pack fails."""


# Curated subset of `tesseract-ocr/tessdata_fast` at `TESSDATA_FAST_COMMIT`.
# Codes not listed here still work if the user installs a `.traineddata` file
# manually and sets `TESSDATA_PREFIX`; only this curated set is auto-fetchable.
KNOWN_LANGUAGES: dict[str, LanguagePackInfo] = {
    "afr": LanguagePackInfo("Afrikaans", "126d480bfae95be2a911ed4916465e27bde75fea2da631e21b96762e5f239646", 2652786),
    "ara": LanguagePackInfo("Arabic", "e3206d3dc87fd50c24a0fb9f01838615911d25168f4e64415244b67d2bb3e729", 1432056),
    "ces": LanguagePackInfo("Czech", "934bcaf97ef3348413263331131c9fa7f55f30db333c711929c124fb635f7e1b", 3795684),
    "chi_sim": LanguagePackInfo("Chinese (Simplified)", "a5fcb6f0db1e1d6d8522f39db4e848f05984669172e584e8d76b6b3141e1f730", 2469156),
    "chi_tra": LanguagePackInfo("Chinese (Traditional)", "529c5b5797d64b126065cd55f2bb4c7fd7b15790798091b1ff259941a829330b", 2366642),
    "dan": LanguagePackInfo("Danish", "acb1fd074487a31d1294fcdfd7d7c673467ffd8aeacb2ccd61ebcbf04eb4e2fa", 2580059),
    "deu": LanguagePackInfo("German", "19d219bbb6672c869d20a9636c6816a81eb9a71796cb93ebe0cb1530e2cdb22d", 1525436),
    "ell": LanguagePackInfo("Greek", "4fba8a0b461038d51f1c20d043d4f2ac38c4e778f1b90830847f7bd8fa3ba726", 1419514),
    "fin": LanguagePackInfo("Finnish", "61a04cd62b507c3d9ae0e1cda399e6715ebf49dea9df47897c8acdcd3bd3e13c", 7865732),
    "fra": LanguagePackInfo("French", "ced037562e8c80c13122dece28dd477d399af80911a28791a66a63ac1e3445ca", 1130365),
    "heb": LanguagePackInfo("Hebrew", "11f9e43ab227f786352a50f75c94c2e9906f1baba86d93276da19da7ce0904db", 961404),
    "hin": LanguagePackInfo("Hindi", "4c73ffc59d497c186b19d1e90f5d721d678ea6b2e277b719bee4e2af12271825", 1122751),
    "hrv": LanguagePackInfo("Croatian", "9e515d9832ce259dbab550b1cc6b998f8b929faf2edacaaca981b05adb130571", 4103348),
    "hun": LanguagePackInfo("Hungarian", "35067e7cfe102dcdc953f9a758fdfaa6296b17a1ee6d874ee780fa306430b9fb", 5296273),
    "ind": LanguagePackInfo("Indonesian", "69786901da87ab8766c1ea7fbb10b28f2110c14da3f6c8f2735df131fba95d88", 1122661),
    "ita": LanguagePackInfo("Italian", "b8f89e1e785118dac4d51ae042c029a64edb5c3ee42ef73027a6d412748d8827", 2701314),
    "jpn": LanguagePackInfo("Japanese", "1f5de9236d2e85f5fdf4b3c500f2d4926f8d9449f28f5394472d9e8d83b91b4d", 2471260),
    "kor": LanguagePackInfo("Korean", "6b85e11d9bbf07863b97b3523b1b112844c43e713df8b66418a081fd1060b3b2", 1677415),
    "msa": LanguagePackInfo("Malay", "e41a3e5febfec50c90371eb1cbb17a48b10cad387900e3420b1f134c1b766cba", 1747801),
    "nld": LanguagePackInfo("Dutch", "ced0e5e046a84c908a6aa7accbef9a232c4a5d9a8276691b81c6ee64d02963f6", 6050296),
    "nor": LanguagePackInfo("Norwegian", "0451eb4f8049ae78196806bf878a389a2f40f1386fe038568cf4441226ba6ef2", 3610079),
    "pol": LanguagePackInfo("Polish", "c4476cdbc0e33d898d32345122b7be1cbf85ace15f920f06c7714756e1ef79b2", 4765518),
    "por": LanguagePackInfo("Portuguese", "c4932b937207a9514b7514d518b931a99938c02a28a5a5a553f8599ed58b7deb", 1982756),
    "ron": LanguagePackInfo("Romanian", "9adfde6b51ba4b97efd10ea37c3070fd3fc2bad7815e81f5c3c198cd96216cc9", 2376323),
    "rus": LanguagePackInfo("Russian", "e16e5e036cce1d9ec2b00063cf8b54472625b9e14d893a169e2b0dedeb4df225", 3861738),
    "spa": LanguagePackInfo("Spanish", "6f2e04d02774a18f01bed44b1111f2cd7f3ba7ac9dc4373cd3f898a40ea6b464", 2294433),
    "swe": LanguagePackInfo("Swedish", "f7304988d41f833efebcc2d529df54b1903ecebbc3da1faabd19a0fddd4fe586", 4167034),
    "tha": LanguagePackInfo("Thai", "294227cc2d1292b0acb28d61d4115c88252b96d466ca90b417cf4cf0c67bf07c", 1072600),
    "tur": LanguagePackInfo("Turkish", "7393381111e1152420fc4092cb44eef4237580d21b92bf30d7d221aad192c6b7", 4550554),
    "ukr": LanguagePackInfo("Ukrainian", "d59e53e2bded32f4445f124b4b00240fcac7e8044c003ab822ccb94f0b3db59b", 3825102),
    "vie": LanguagePackInfo("Vietnamese", "79df64caf7bcfb2a27df5042ecb6121e196eada34da774956995747636d5bfa1", 531275),
}

# Human-readable names for bundled codes that aren't in KNOWN_LANGUAGES (currently
# just English). Kept separate so KNOWN_LANGUAGES only lists downloadable codes.
_BUNDLED_NAMES = {"eng": "English"}

ProgressCallback = Callable[[str, int, int], None]
"""``(language_code, bytes_downloaded, total_bytes)``, called repeatedly while
downloading one language code. ``total_bytes`` falls back to the registry's
pinned size when the server omits ``Content-Length``."""


# Tesseract codes are identifiers, not paths. Reject anything that could
# traverse out of the tessdata directory (``../``, separators) before
# ``is_file`` / copy / download ever see it.
_LANGUAGE_CODE_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")


def _split_language_codes(language: str) -> list[str]:
    return [part.strip() for part in (language or "").split("+") if part.strip()]


def is_valid_language_code(code: str) -> bool:
    """Return True when ``code`` is a single safe Tesseract language identifier."""
    if not code or ".." in code or "/" in code or "\\" in code:
        return False
    return _LANGUAGE_CODE_RE.fullmatch(code) is not None


def validate_ocr_language(language: str) -> list[str]:
    """Split ``+``-joined codes, raising ``ValueError`` if empty or unsafe."""
    codes = _split_language_codes(language)
    if not codes:
        raise ValueError("ocr_language must not be empty")
    invalid = [code for code in codes if not is_valid_language_code(code)]
    if invalid:
        raise ValueError(
            "Invalid OCR language code(s): "
            + ", ".join(repr(code) for code in invalid)
            + ". Each code must match [A-Za-z][A-Za-z0-9_]* "
            "(for example 'eng' or 'chi_sim') and may be joined with '+'."
        )
    return codes


def _traineddata_path(directory: Path, code: str) -> Path:
    """Return ``directory / code.traineddata``, refusing path-like codes."""
    if not is_valid_language_code(code):
        raise ValueError(
            f"Invalid OCR language code: {code!r}. "
            "Each code must match [A-Za-z][A-Za-z0-9_]*."
        )
    root = directory.resolve()
    path = (root / f"{code}.traineddata").resolve()
    if path.parent != root:
        raise ValueError(f"Invalid OCR language code: {code!r}")
    return path


def is_bundled(code: str) -> bool:
    """Return True when ``code`` ships inside VERA and needs no download."""
    if not is_valid_language_code(code):
        return False
    return (_BUNDLED_DIR / f"{code}.traineddata").is_file()


def is_known(code: str) -> bool:
    """Return True when ``code`` is bundled or in the curated download registry."""
    if not is_valid_language_code(code):
        return False
    return is_bundled(code) or code in KNOWN_LANGUAGES


def known_language_codes() -> list[str]:
    """Sorted codes usable for OCR without a manual ``TESSDATA_PREFIX`` install."""
    bundled = {path.stem for path in _BUNDLED_DIR.glob("*.traineddata")}
    return sorted(bundled | set(KNOWN_LANGUAGES))


def language_choice_labels() -> list[tuple[str, str]]:
    """Return ``(code, \"Name (code)\")`` pairs for bundled + downloadable languages.

    English is listed first; remaining codes are sorted by display name. Labels
    use the same Tesseract language codes documented upstream (for example
    ``spa``, not ``es``). Codes outside this list still work with a manual
    ``TESSDATA_PREFIX`` install but are not advertised for one-click download.
    """
    rows: list[tuple[str, str]] = []
    for code in known_language_codes():
        name = _BUNDLED_NAMES.get(code) or KNOWN_LANGUAGES[code].name
        rows.append((code, f"{name} ({code})"))
    eng = [row for row in rows if row[0] == "eng"]
    rest = sorted((row for row in rows if row[0] != "eng"), key=lambda row: row[1].casefold())
    return eng + rest


def describe_language_codes(language: str | None = None) -> list[dict[str, object]]:
    """Return status metadata for known languages, or specific ``+``-joined codes.

    Each entry has ``code``, ``name``, ``bundled``, ``downloadable``, ``cached``,
    and (when known) ``size_bytes``. Unknown explicit codes are still listed with
    ``downloadable: False`` and no ``size_bytes`` so a UI can explain that a
    manual ``TESSDATA_PREFIX`` install is required.
    """
    codes = _split_language_codes(language) if language else known_language_codes()
    cache = default_cache_dir()
    entries: list[dict[str, object]] = []
    for code in codes:
        bundled = is_bundled(code)
        info = KNOWN_LANGUAGES.get(code)
        cached = bundled or _is_valid_cached_file(cache / f"{code}.traineddata", code)
        entry: dict[str, object] = {
            "code": code,
            "name": _BUNDLED_NAMES.get(code) or (info.name if info else code),
            "bundled": bundled,
            "downloadable": bundled or info is not None,
            "cached": cached,
        }
        if info is not None:
            entry["size_bytes"] = info.size
        entries.append(entry)
    return entries


def default_cache_dir() -> Path:
    """Per-user cache directory for downloaded language packs.

    Override with the ``VERA_TESSDATA_CACHE`` environment variable. Otherwise
    uses a platform-conventional cache location; nothing is created until a
    download actually happens.
    """
    override = os.environ.get("VERA_TESSDATA_CACHE")
    if override:
        return Path(override).expanduser()
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(base) / "vera" / "tessdata"
    xdg = os.environ.get("XDG_CACHE_HOME")
    base = Path(xdg).expanduser() if xdg else Path.home() / ".cache"
    return base / "vera" / "tessdata"


def _is_valid_cached_file(path: Path, code: str) -> bool:
    if not is_valid_language_code(code) or not path.is_file():
        return False
    info = KNOWN_LANGUAGES.get(code)
    if info is None:
        # Not in the registry (e.g. a bundled file copied into the cache for a
        # mixed "+" combination) — presence is the only signal available.
        return path.stat().st_size > 0
    if path.stat().st_size != info.size:
        return False
    return _sha256_file(path) == info.sha256


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _download_one(
    code: str,
    destination: Path,
    *,
    progress: ProgressCallback | None,
    timeout: float,
) -> None:
    if not is_valid_language_code(code):
        raise ValueError(
            f"Invalid OCR language code: {code!r}. "
            "Each code must match [A-Za-z][A-Za-z0-9_]*."
        )
    info = KNOWN_LANGUAGES.get(code)
    if info is None:
        known = ", ".join(sorted(KNOWN_LANGUAGES)) or "(none)"
        raise UnknownOCRLanguageError(
            f"OCR language {code!r} has no bundled data and is not in VERA's "
            f"download registry. Downloadable codes: {known}. Install a "
            "Tesseract .traineddata file manually and set TESSDATA_PREFIX instead."
        )
    url = f"{_TESSDATA_FAST_BASE_URL}/{code}.traineddata"
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, tmp_name = tempfile.mkstemp(
        prefix=f".{code}.", suffix=".part", dir=destination.parent
    )
    os.close(descriptor)
    tmp_path = Path(tmp_name)
    try:
        request = urllib.request.Request(url, headers={"User-Agent": "vera-ingest"})
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                total = int(response.headers.get("Content-Length") or info.size)
                downloaded = 0
                with tmp_path.open("wb") as handle:
                    while True:
                        chunk = response.read(_DOWNLOAD_CHUNK_SIZE)
                        if not chunk:
                            break
                        handle.write(chunk)
                        downloaded += len(chunk)
                        if downloaded > info.size:
                            raise OCRLanguageDownloadError(
                                f"Downloaded OCR language data for {code!r} exceeded "
                                f"pinned size {info.size} bytes; discarded."
                            )
                        if progress:
                            progress(code, downloaded, total)
        except OCRLanguageDownloadError:
            raise
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise OCRLanguageDownloadError(
                f"Could not download OCR language data for {code!r} from {url}: {exc}"
            ) from exc
        actual_hash = _sha256_file(tmp_path)
        actual_size = tmp_path.stat().st_size
        if actual_hash != info.sha256 or actual_size != info.size:
            raise OCRLanguageDownloadError(
                f"Downloaded OCR language data for {code!r} failed integrity "
                f"verification (expected sha256={info.sha256} size={info.size}; "
                f"got sha256={actual_hash} size={actual_size}). Discarded."
            )
        os.replace(tmp_path, destination)
    finally:
        tmp_path.unlink(missing_ok=True)


def ensure_language_data(
    language: str,
    *,
    allow_download: bool,
    cache_dir: Path | None = None,
    progress: ProgressCallback | None = None,
    timeout: float = 30.0,
) -> str | None:
    """Return a tessdata directory covering every ``+``-joined code, or ``None``.

    Bundled-only requests resolve immediately with no filesystem writes (the
    default English path is unaffected). Mixed requests (bundled + cached or
    downloadable codes) always copy bundled files into ``cache_dir`` so
    PyMuPDF can load every code from one directory, even when download is
    off. When any requested code is still missing:

    - If ``allow_download`` is False, returns ``None`` so the caller can raise
      its existing manual-install error.
    - If ``allow_download`` is True, downloads missing known codes into
      ``cache_dir`` (default: :func:`default_cache_dir`). Raises
      :class:`UnknownOCRLanguageError` for codes with no bundled or
      registry data, and :class:`OCRLanguageDownloadError` if a download
      fails or fails integrity verification.
    """
    codes = _split_language_codes(language)
    if not codes:
        return None
    codes = validate_ocr_language(language)

    if all(is_bundled(code) for code in codes):
        return str(_BUNDLED_DIR)

    cache = cache_dir or default_cache_dir()

    def cache_file(code: str) -> Path:
        return _traineddata_path(cache, code)

    # Assemble bundled codes into the cache even when download is off.
    # PyMuPDF needs every "+" code in one directory; TESSDATA_PREFIX alone
    # would miss VERA's bundled English.
    for code in codes:
        if is_bundled(code) and not _is_valid_cached_file(cache_file(code), code):
            cache.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(_traineddata_path(_BUNDLED_DIR, code), cache_file(code))

    missing = [code for code in codes if not _is_valid_cached_file(cache_file(code), code)]
    if not missing:
        return str(cache)
    if not allow_download:
        return None

    for code in missing:
        destination = cache_file(code)
        if is_bundled(code):
            cache.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(_traineddata_path(_BUNDLED_DIR, code), destination)
            continue
        _download_one(code, destination, progress=progress, timeout=timeout)
    return str(cache)


# Public aliases with `vera_ingest`-level names, used by the CLI and desktop
# app to pre-fetch language packs outside of a PDF conversion.
default_ocr_language_cache_dir = default_cache_dir
describe_ocr_languages = describe_language_codes


def download_ocr_language_data(
    language: str,
    *,
    cache_dir: Path | None = None,
    progress: ProgressCallback | None = None,
    timeout: float = 30.0,
) -> str:
    """Explicitly fetch (or reuse cached) data for ``language``, returning its directory.

    Unlike :func:`ensure_language_data`, this always attempts a download for
    missing codes — intended for an explicit "download this language pack"
    action rather than an implicit fallback during OCR.
    """
    validate_ocr_language(language)
    resolved = ensure_language_data(
        language,
        allow_download=True,
        cache_dir=cache_dir,
        progress=progress,
        timeout=timeout,
    )
    assert resolved is not None  # allow_download=True never returns None
    return resolved
