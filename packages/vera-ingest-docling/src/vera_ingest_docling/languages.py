"""RapidOCR language codes and Tesseract → RapidOCR mapping."""

from __future__ import annotations

# RapidOCR onnxruntime language codes observed from the installed engine.
# Keep in sync with RapidOCR's supported recognition languages.
RAPIDOCR_LANGS = frozenset(
    {
        "af",
        "arabic",
        "az",
        "bs",
        "ca",
        "ch",
        "chinese_cht",
        "cs",
        "cy",
        "cyrillic",
        "da",
        "de",
        "devanagari",
        "el",
        "en",
        "es",
        "eslav",
        "et",
        "eu",
        "fi",
        "fr",
        "french",
        "ga",
        "german",
        "gl",
        "hr",
        "hu",
        "id",
        "is",
        "it",
        "japan",
        "korean",
        "ku",
        "la",
        "latin",
        "lb",
        "lt",
        "lv",
        "mi",
        "ms",
        "mt",
        "nl",
        "no",
        "oc",
        "pl",
        "pt",
        "qu",
        "rm",
        "ro",
        "rs_latin",
        "sk",
        "sl",
        "sq",
        "sv",
        "sw",
        "ta",
        "te",
        "th",
        "tl",
        "tr",
        "uz",
        "vi",
    }
)

# Common Tesseract / ISO-639-3 codes (VERA CLI default is ``eng``) → RapidOCR.
TESSERACT_TO_RAPIDOCR = {
    "afr": "af",
    "ara": "arabic",
    "aze": "az",
    "bos": "bs",
    "bul": "cyrillic",
    "cat": "ca",
    "ces": "cs",
    "chi_sim": "ch",
    "chi_tra": "chinese_cht",
    "cym": "cy",
    "cze": "cs",
    "dan": "da",
    "deu": "de",
    "dut": "nl",
    "ell": "el",
    "eng": "en",
    "est": "et",
    "eus": "eu",
    "baq": "eu",
    "fin": "fi",
    "fra": "fr",
    "fre": "fr",
    "ger": "de",
    "gle": "ga",
    "glg": "gl",
    "gre": "el",
    "hin": "devanagari",
    "hrv": "hr",
    "hun": "hu",
    "ice": "is",
    "ind": "id",
    "isl": "is",
    "ita": "it",
    "jpn": "japan",
    "kor": "korean",
    "kur": "ku",
    "lat": "la",
    "lav": "lv",
    "lit": "lt",
    "ltz": "lb",
    "may": "ms",
    "mlt": "mt",
    "mri": "mi",
    "msa": "ms",
    "nld": "nl",
    "nor": "no",
    "oci": "oc",
    "pol": "pl",
    "por": "pt",
    "que": "qu",
    "roh": "rm",
    "ron": "ro",
    "rum": "ro",
    "rus": "cyrillic",
    "san": "devanagari",
    "slk": "sk",
    "slo": "sk",
    "slv": "sl",
    "spa": "es",
    "sqi": "sq",
    "alb": "sq",
    "swa": "sw",
    "swe": "sv",
    "tam": "ta",
    "tel": "te",
    "tgl": "tl",
    "fil": "tl",
    "tha": "th",
    "tur": "tr",
    "ukr": "cyrillic",
    "uzb": "uz",
    "vie": "vi",
}


def map_rapidocr_languages(ocr_language: str | None) -> list[str]:
    """Map VERA/Tesseract OCR language codes to RapidOCR language codes.

    VERA's default ``eng`` is Tesseract-style; RapidOCR expects ``en``. Accepts
    ``+`` or ``,`` separated lists and passes through codes that are already
    RapidOCR-native.
    """
    raw = (ocr_language or "eng").strip()
    if not raw:
        raw = "eng"
    parts = [part.strip().lower() for part in raw.replace("+", ",").split(",") if part.strip()]
    if not parts:
        parts = ["eng"]

    mapped: list[str] = []
    unknown: list[str] = []
    for part in parts:
        rapid = TESSERACT_TO_RAPIDOCR.get(part, part)
        # Prefer canonical short codes when RapidOCR aliases exist.
        if rapid == "french":
            rapid = "fr"
        elif rapid == "german":
            rapid = "de"
        if rapid not in RAPIDOCR_LANGS:
            unknown.append(part)
            continue
        if rapid not in mapped:
            mapped.append(rapid)

    if unknown:
        supported = ", ".join(sorted(RAPIDOCR_LANGS))
        raise ValueError(
            "Docling/RapidOCR does not support OCR language "
            f"{', '.join(unknown)!r} (from {ocr_language!r}). "
            "Use a RapidOCR code such as 'en', or a mapped Tesseract alias "
            f"such as 'eng'. Supported RapidOCR codes: {supported}."
        )
    return mapped
