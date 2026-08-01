"""
comment_cleaner.py

Membersihkan comments.json (struktur tree native: setiap komentar punya
field `replies` berisi list komentar anak dengan struktur sama).

Transformasi yang dilakukan (semua bisa di-toggle via pipeline_config.yaml):
- strip HTML markup, ekstrak <a href> ke field `links` terpisah
- hapus zero-width space & rapikan mention yang menempel ke pesan
- deteksi komentar duplikat persis (exact match teks, per top-level comment)
- normalisasi angka desimal locale ID (konsisten dengan transcript)
- (opsional, default off) normalisasi slang & terminologi
- tandai is_channel_owner (author == channel pemilik video, dari metadata)
- flagging: numeric_claim/truncated_unit_suspect/price_mention (regex umum,
  sama seperti transcript) + price_mention_ambiguous (angka polos + kata
  kunci harga di komentar yang sama)

Desain: text_raw selalu dipertahankan berdampingan dengan text_clean -
tidak ada mutasi destruktif, supaya bisa di-audit balik ke sumber asli.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from cleaners.base import Cleaner, CleaningReport
from cleaners.flagging import detect_flags
from cleaners.html_utils import extract_links, strip_html, remove_zero_width_chars
from cleaners.text_normalizer import collapse_whitespace, apply_dictionary, normalize_decimal_numbers


def _normalize_identity(name: str) -> str:
    """Normalisasi nama untuk perbandingan author vs channel: lowercase,
    hapus '@', hapus spasi. Perlu karena formatnya beda antar sumber
    (author komentar "bongkarcordless" vs metadata.channel "Bongkar Cordless").
    """
    return name.lstrip("@").lower().replace(" ", "")


def _has_ambiguous_price_mention(text: str, bare_number_pattern: str, context_keywords: list[str]) -> bool:
    """True jika `text` mengandung angka polos (tanpa satuan harga eksplisit)
    DAN salah satu kata kunci konteks harga muncul di teks yang sama.

    Sengaja tidak diproses lewat cleaners/flagging.py::detect_flags() karena
    butuh scan seluruh teks komentar (cari kata kunci), bukan cuma match
    regex lokal di titik angkanya - lihat catatan di price_context.yaml.
    """
    if not re.search(bare_number_pattern, text):
        return False
    text_lower = text.lower()
    return any(re.search(rf"\b{re.escape(kw)}\b", text_lower) for kw in context_keywords)


def _collect_authors(comments: list[dict]) -> set[str]:
    """Kumpulkan semua username (tanpa '@') dari seluruh tree, dipakai untuk
    memisahkan mention yang menempel ke pesan (mis. "@fooBALASAN" -> "@foo BALASAN"),
    karena kita punya daftar username valid dari data itu sendiri - bukan tebakan.
    """
    authors: set[str] = set()

    def _walk(nodes: list[dict]) -> None:
        for node in nodes:
            author = node.get("author", "")
            authors.add(author.lstrip("@"))
            _walk(node.get("replies", []))

    _walk(comments)
    # urutkan terpanjang dulu supaya "bongkarcordless" tidak ke-shadow oleh prefix lebih pendek
    return authors


def _split_stuck_mention(text: str, authors: set[str]) -> str:
    """Sisipkan spasi antara @mention dan pesan yang menempel, menggunakan
    daftar username valid dari dataset itu sendiri sebagai referensi.
    """
    if not text.startswith("@"):
        return text
    for author in sorted(authors, key=len, reverse=True):
        prefix = "@" + author
        if text.startswith(prefix) and len(text) > len(prefix) and text[len(prefix)] != " ":
            return prefix + " " + text[len(prefix):]
    return text


@dataclass
class _CleanContext:
    apply_slang: bool
    apply_terminology: bool
    strip_html_flag: bool
    extract_links_flag: bool
    normalize_mentions: bool
    normalize_numbers: bool
    enable_flagging: bool
    dictionaries: dict
    authors: set[str]
    seen_exact_texts: set[str]
    channel_identity: str | None


class CommentCleaner(Cleaner):
    stage_name = "comments"

    def __init__(self, config: dict, dictionaries: dict, channel_name: str | None = None):
        """
        Args:
            channel_name: nama channel dari metadata.json (mis. "Bongkar Cordless"),
                dipakai untuk tandai is_channel_owner. Parameter khusus
                CommentCleaner - tidak mengubah kontrak Cleaner dasar di base.py,
                karena hanya cleaner ini yang butuh konteks channel.
        """
        super().__init__(config, dictionaries)
        self.channel_identity = _normalize_identity(channel_name) if channel_name else None

    def clean(self, raw_data: list[dict], dataset_id: str):
        report = CleaningReport(stage_name=self.stage_name)
        authors = _collect_authors(raw_data)

        ctx = _CleanContext(
            apply_slang=self.config.get("normalize_slang", False),
            apply_terminology=self.config.get("apply_terminology_correction", False),
            strip_html_flag=self.config.get("strip_html", True),
            extract_links_flag=self.config.get("extract_links", True),
            normalize_mentions=self.config.get("normalize_mentions", True),
            normalize_numbers=self.config.get("normalize_numbers", True),
            enable_flagging=self.config.get("enable_flagging", True),
            dictionaries=self.dictionaries,
            authors=authors,
            seen_exact_texts=set(),
            channel_identity=self.channel_identity,
        )

        dedup_enabled = self.config.get("dedup_exact_match", True)
        cleaned = [
            self._clean_node(node, ctx, report, dedup_enabled, comment_id_prefix="")
            for node in raw_data
        ]
        return cleaned, report

    def _clean_node(
        self,
        node: dict,
        ctx: _CleanContext,
        report: CleaningReport,
        dedup_enabled: bool,
        comment_id_prefix: str,
    ) -> dict:
        report.items_processed += 1
        text_raw = node.get("text", "")
        text = text_raw

        links: list[str] = []
        if ctx.extract_links_flag:
            links = extract_links(text)

        if ctx.strip_html_flag:
            text = strip_html(text)

        text = remove_zero_width_chars(text)

        if ctx.normalize_mentions:
            text = _split_stuck_mention(text, ctx.authors)

        text = collapse_whitespace(text)

        modified = text != text_raw
        dict_corrected = False

        if ctx.apply_terminology:
            text, changed = apply_dictionary(text, ctx.dictionaries.get("terminology_map", {}))
            modified = modified or changed
            dict_corrected = dict_corrected or changed
        if ctx.apply_slang:
            text, changed = apply_dictionary(text, ctx.dictionaries.get("slang_map", {}))
            modified = modified or changed
            dict_corrected = dict_corrected or changed
        if ctx.normalize_numbers:
            new_text = normalize_decimal_numbers(text)
            modified = modified or (new_text != text)
            text = new_text

        is_duplicate = False
        min_length = self.config.get("dedup_min_length", 0)
        if dedup_enabled and len(text.strip()) >= min_length:
            normalized_for_dedup = text.strip().lower()
            if normalized_for_dedup in ctx.seen_exact_texts:
                is_duplicate = True
                report.duplicates_flagged += 1
            else:
                ctx.seen_exact_texts.add(normalized_for_dedup)

        if modified:
            report.items_modified += 1

        is_channel_owner = (
            ctx.channel_identity is not None
            and _normalize_identity(node.get("author", "")) == ctx.channel_identity
        )

        flags: list[str] = []
        if ctx.enable_flagging:
            flags = detect_flags(text, ctx.dictionaries.get("flagging_patterns", {}), dict_corrected)
            price_ctx = ctx.dictionaries.get("price_context", {})
            if price_ctx and _has_ambiguous_price_mention(
                text, price_ctx.get("bare_number_pattern", r"\b\d{2,4}\b"), price_ctx.get("context_keywords", [])
            ):
                flags.append("price_mention_ambiguous")
            if flags:
                report.flagged_for_review += 1

        cleaned_replies = [
            self._clean_node(child, ctx, report, dedup_enabled, comment_id_prefix)
            for child in node.get("replies", [])
        ]

        return {
            "id": node.get("id"),
            "author": node.get("author"),
            "is_channel_owner": is_channel_owner,
            "text_raw": text_raw,
            "text_clean": text,
            "links": links,
            "likes": node.get("likes", 0),
            "timestamp": node.get("timestamp"),
            "is_duplicate": is_duplicate,
            "flags": flags,
            "needs_review": len(flags) > 0,
            "replies": cleaned_replies,
        }
