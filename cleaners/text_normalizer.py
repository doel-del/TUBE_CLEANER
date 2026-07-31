"""
text_normalizer.py

Utility teks generik yang dipakai lintas cleaner (comment & transcript):
- normalisasi whitespace
- normalisasi angka desimal locale Indonesia (koma -> titik)
- penerapan dictionary koreksi (slang/brand/terminology) secara whole-word,
  case-preserving pada huruf pertama.

Tidak spesifik ke satu jenis data - murni fungsi teks agar bisa dipakai ulang
tanpa duplikasi logic di comment_cleaner.py maupun transcript_cleaner.py.
"""

from __future__ import annotations

import re

_WHITESPACE_PATTERN = re.compile(r"\s+")
_DECIMAL_COMMA_PATTERN = re.compile(r"(?<=\d),(?=\d)")


def collapse_whitespace(text: str) -> str:
    return _WHITESPACE_PATTERN.sub(" ", text).strip()


def normalize_decimal_numbers(text: str) -> str:
    """Ubah koma desimal gaya Indonesia ("0,75") jadi titik ("0.75").

    Hanya menyentuh koma yang diapit digit di kedua sisi, supaya tidak merusak
    koma sebagai tanda baca kalimat biasa (mis. "Oke, seperti ini").
    """
    return _DECIMAL_COMMA_PATTERN.sub(".", text)


def apply_dictionary(text: str, mapping: dict[str, str]) -> tuple[str, bool]:
    """Terapkan koreksi whole-word, case-insensitive, dari `mapping`.

    Mengembalikan (text_baru, ada_perubahan). Menjaga huruf kapital di awal
    kata asli (mis. "Klo" di awal kalimat -> "Kalo", bukan "kalo") agar hasil
    tidak merusak kapitalisasi kalimat.

    Catatan: entri di `mapping` bisa berisi frasa multi-kata (mis.
    "impeck dril"), bukan cuma satu kata - regex dibangun dari key mapping
    langsung sehingga mendukung keduanya.
    """
    if not mapping:
        return text, False

    changed = False
    lower_mapping = {k.lower(): v for k, v in mapping.items()}
    # urutkan key terpanjang dulu supaya frasa multi-kata (mis. "impeck dril")
    # cocok sebelum sub-katanya sendiri ter-match parsial
    keys_sorted = sorted(lower_mapping.keys(), key=len, reverse=True)
    pattern = re.compile(
        r"\b(" + "|".join(re.escape(k) for k in keys_sorted) + r")\b",
        re.IGNORECASE,
    )

    def _replace(match: re.Match) -> str:
        nonlocal changed
        original = match.group(0)
        replacement = lower_mapping[original.lower()]
        if original[0].isupper():
            replacement = replacement[0].upper() + replacement[1:]
        changed = True
        return replacement

    new_text = pattern.sub(_replace, text)
    return new_text, changed
