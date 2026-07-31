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


def detect_flags(text: str, patterns: dict, dictionary_corrected: bool) -> list[str]:
    """Cek `text` terhadap semua pola di `patterns` (dari flagging_patterns.yaml).

    Args:
        text: text_clean kalimat (setelah semua cleaning stage lain selesai).
        patterns: dict {flag_name: [list_of_regex]} dari flagging_patterns.yaml.
        dictionary_corrected: True jika brand/terminology correction sempat
            mengubah kalimat ini (dihitung di transcript_cleaner.py).

    Returns:
        List nama flag yang cocok, urutan sesuai urutan di config.
        List kosong berarti kalimat ini tidak dicurigai bermasalah.
    """
    flags: list[str] = []

    for flag_name, regex_list in patterns.items():
        for pattern in regex_list:
            if re.search(pattern, text, re.IGNORECASE):
                flags.append(flag_name)
                break

    if dictionary_corrected and "dictionary_corrected" not in flags:
        flags.append("dictionary_corrected")

    return flags
