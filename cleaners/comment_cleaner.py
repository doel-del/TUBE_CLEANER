"""
comment_cleaner.py

Membersihkan comments.json (struktur tree native: setiap komentar punya
field `replies` berisi list komentar anak dengan struktur sama).

Transformasi yang dilakukan (semua bisa di-toggle via pipeline_config.yaml):
- strip HTML markup, ekstrak <a href> ke field `links` terpisah
- hapus zero-width space & rapikan mention yang menempel ke pesan
- deteksi komentar duplikat persis (exact match teks, per top-level comment)
- (opsional, default off) normalisasi slang & terminologi

Desain: text_raw selalu dipertahankan berdampingan dengan text_clean -
tidak ada mutasi destruktif, supaya bisa di-audit balik ke sumber asli.
"""

from __future__ import annotations

from dataclasses import dataclass

from cleaners.base import Cleaner, CleaningReport
from cleaners.html_utils import extract_links, strip_html, remove_zero_width_chars
from cleaners.text_normalizer import collapse_whitespace, apply_dictionary


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
    dictionaries: dict
    authors: set[str]
    seen_exact_texts: set[str]


class CommentCleaner(Cleaner):
    stage_name = "comments"

    def clean(self, raw_data: list[dict], dataset_id: str):
        report = CleaningReport(stage_name=self.stage_name)
        authors = _collect_authors(raw_data)

        ctx = _CleanContext(
            apply_slang=self.config.get("normalize_slang", False),
            apply_terminology=self.config.get("apply_terminology_correction", False),
            strip_html_flag=self.config.get("strip_html", True),
            extract_links_flag=self.config.get("extract_links", True),
            normalize_mentions=self.config.get("normalize_mentions", True),
            dictionaries=self.dictionaries,
            authors=authors,
            seen_exact_texts=set(),
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

        if ctx.apply_terminology:
            text, changed = apply_dictionary(text, ctx.dictionaries.get("terminology_map", {}))
            modified = modified or changed
        if ctx.apply_slang:
            text, changed = apply_dictionary(text, ctx.dictionaries.get("slang_map", {}))
            modified = modified or changed

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

        cleaned_replies = [
            self._clean_node(child, ctx, report, dedup_enabled, comment_id_prefix)
            for child in node.get("replies", [])
        ]

        return {
            "id": node.get("id"),
            "author": node.get("author"),
            "text_raw": text_raw,
            "text_clean": text,
            "links": links,
            "likes": node.get("likes", 0),
            "timestamp": node.get("timestamp"),
            "is_duplicate": is_duplicate,
            "replies": cleaned_replies,
        }
