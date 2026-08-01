"""
flagging.py

Menandai kalimat transcript yang berisiko mengandung ASR error / data loss
pada klaim numerik-teknis (angka+satuan), TANPA mengubah teksnya sama sekali.

Tujuan: kalimat rawan (mis. "8A" yang mestinya "8Ah", angka yang terpotong)
tetap dibiarkan apa adanya di text_clean, tapi ditandai `flags` supaya proses
Claim Extraction downstream memperlakukannya dengan confidence lebih rendah -
bukan langsung dipercaya sebagai fakta tanpa verifikasi silang.

Modul ini murni annotator (read-only), bukan cleaner - karena itu sengaja
dipisah dari cleaners/*.py yang mengubah teks. Menambah aturan flag baru
cukup edit config/dictionaries/flagging_patterns.yaml, tidak perlu sentuh
modul ini.
"""

from __future__ import annotations

import re


def _matches_excluding_suffix(text: str, pattern: str, exclude_suffixes: set[str]) -> bool:
    """Cek pattern match di text, TAPI skip match yang suffix hurufnya ada di
    exclude_suffixes (dianggap unit yang sudah lengkap, bukan terpotong).

    Contoh: pattern '\\d+[A-Za-z]{1,2}\\b' cocok baik ke "8A" (curiga terpotong)
    maupun "8Ah" (sudah lengkap & sah). exclude_suffixes={"ah"} membuat "8Ah"
    dilewati sementara "8A" tetap ter-flag.
    """
    for m in re.finditer(pattern, text, re.IGNORECASE):
        suffix = re.search(r"[A-Za-z]+$", m.group(0))
        suffix_text = suffix.group(0).lower() if suffix else ""
        if suffix_text not in exclude_suffixes:
            return True
    return False


def detect_flags(text: str, patterns: dict, dictionary_corrected: bool) -> list[str]:
    """Cek `text` terhadap semua pola di `patterns` (dari flagging_patterns.yaml).

    Args:
        text: text_clean (setelah semua cleaning stage lain selesai).
        patterns: dict {flag_name: rule} dari flagging_patterns.yaml, dimana
            `rule` bisa berupa:
              - list of regex (bentuk lama, tetap didukung)
              - dict {"patterns": [...], "exclude_if_suffix_in": [...]}
                untuk rule yang butuh pengecualian (lihat truncated_unit_suspect).
        dictionary_corrected: True jika brand/terminology correction sempat
            mengubah teks ini.

    Returns:
        List nama flag yang cocok. List kosong = tidak dicurigai bermasalah.
    """
    flags: list[str] = []

    for flag_name, rule in patterns.items():
        if isinstance(rule, dict):
            regex_list = rule.get("patterns", [])
            exclude_suffixes = {s.lower() for s in rule.get("exclude_if_suffix_in", [])}
        else:
            regex_list = rule
            exclude_suffixes = set()

        for pattern in regex_list:
            if exclude_suffixes:
                matched = _matches_excluding_suffix(text, pattern, exclude_suffixes)
            else:
                matched = bool(re.search(pattern, text, re.IGNORECASE))
            if matched:
                flags.append(flag_name)
                break

    if dictionary_corrected and "dictionary_corrected" not in flags:
        flags.append("dictionary_corrected")

    return flags
