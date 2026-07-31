"""
html_utils.py

Utility murni untuk menangani markup HTML yang terselip di teks komentar
YouTube (mis. <br>, <a href="...">...</a>). Tidak bergantung pada
comment_cleaner - reusable untuk sumber data lain yang punya masalah sama.
"""

from __future__ import annotations

import html
import re

_TAG_A_PATTERN = re.compile(r'<a\s+[^>]*href="([^"]+)"[^>]*>.*?</a>', re.IGNORECASE | re.DOTALL)
_BR_PATTERN = re.compile(r"<br\s*/?>", re.IGNORECASE)
_ANY_TAG_PATTERN = re.compile(r"<[^>]+>")
_ZWSP_PATTERN = re.compile(r"[\u200b\u200c\u200d\ufeff]")  # zero-width space & sejenisnya


def extract_links(text: str) -> list[str]:
    """Ambil semua URL dari tag <a href="...">, sebelum tag tersebut dihapus."""
    return _TAG_A_PATTERN.findall(text)


def strip_html(text: str) -> str:
    """Hapus tag HTML, ganti <br> dengan spasi, decode HTML entity (&amp; dst)."""
    text = _BR_PATTERN.sub(" ", text)
    text = _ANY_TAG_PATTERN.sub("", text)
    text = html.unescape(text)
    return text


def remove_zero_width_chars(text: str) -> str:
    """Hapus zero-width space yang menyebabkan '@mentiontext' menempel tanpa spasi."""
    return _ZWSP_PATTERN.sub("", text)


def normalize_mention_spacing(text: str) -> str:
    """Tambahkan spasi setelah @mention jika langsung menempel ke kata berikutnya.

    Contoh kasus nyata di dataset: "​@bongkarcordlesssiap tks"
    (setelah ZWSP dihapus jadi "@bongkarcordlesssiap tks" - mention & pesan menyatu).
    Heuristik: mention YouTube selalu diikuti username tanpa spasi, sehingga kita
    tidak bisa menebak batas mention/pesan secara pasti tanpa daftar username.
    Fungsi ini hanya merapikan whitespace di sekitar '@', bukan memisah mention
    dari kata berikutnya (itu butuh daftar username valid, di luar scope stage ini).
    """
    return re.sub(r"\s+", " ", text).strip()
