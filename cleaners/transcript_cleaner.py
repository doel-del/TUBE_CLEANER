"""
transcript_cleaner.py

Membersihkan transcript.json (array chunk ASR granular per-kata/frasa)
menjadi array kalimat utuh yang lebih cocok untuk Claim Extraction.

Tahapan:
1. Sentence re-chunking: gabungkan chunk berturutan jadi 1 kalimat
   berdasarkan tanda baca akhir (. ! ?) DAN gap waktu antar-chunk
   (jika gap > sentence_merge_gap_ms, dianggap batas kalimat baru
   walau tidak ada tanda baca - mengantisipasi ASR yang tidak selalu
   memberi tanda baca).
2. Near-duplicate detection antar-kalimat hasil merge (mis. kasus nyata:
   "Oke, seperti ini dalamnya untuk motornya" yang terekam ulang).
3. Filler removal di batas kalimat (awal/akhir), bukan di tengah -
   supaya tidak merusak makna kalimat yang memang mengandung kata
   tsb sebagai bagian struktur (mis. "ya" sbg partikel penegas di tengah).
4. Koreksi brand & terminologi via dictionary.
5. Normalisasi angka desimal locale ID.
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass

from cleaners.base import Cleaner, CleaningReport
from cleaners.flagging import detect_flags
from cleaners.text_normalizer import (
    collapse_whitespace,
    normalize_decimal_numbers,
    apply_dictionary,
)

_SENTENCE_END_CHARS = (".", "!", "?")
# Menangkap pengulangan kata langsung akibat disfluency ASR, baik yang
# ditulis dengan hubung ("kan-kan") maupun dipisah spasi ("kan kan").
# Hanya kata identik berturut-turut - tidak menyentuh pengulangan yang
# punya jarak/kata lain di antaranya (itu repetisi wajar dalam bahasa lisan).
_STUTTER_PATTERN = re.compile(r"\b(\w+)[-\s]\1\b", re.IGNORECASE)


def _collapse_stutter(text: str, filler_set: set[str]) -> tuple[str, bool]:
    """Gabungkan kata yang terulang langsung jadi satu kata - HANYA jika kata
    tsb ada di daftar filler (partikel diskursus pendek: "kan", "ya", "nih", dst).

    PENTING: tidak boleh diterapkan ke sembarang kata. Bahasa Indonesia punya
    reduplikasi gramatikal yang produktif dan sangat umum (rekan-rekan,
    kecil-kecil, teman-teman) yang secara sintaksis identik dengan stutter
    ASR ("kan-kan") - keduanya "kata-kata". Membedakannya butuh mengetahui
    apakah kata itu leksikal/isi (jangan disentuh) atau partikel diskursus
    (aman digabung). filler_set dari filler_words.yaml dipakai sebagai proxy
    daftar kata yang aman - bukan regex generik pada \\w+ manapun.

    Tidak menyisipkan tanda baca tambahan (lihat catatan modul) karena butuh
    sinyal jeda/prosodi dari audio yang tidak tersedia di transcript teks.
    """
    if not filler_set:
        return text, False

    changed = False

    def _repl(match: re.Match) -> str:
        nonlocal changed
        word = match.group(1)
        if word.lower() not in filler_set:
            return match.group(0)  # bukan filler -> jangan sentuh (mis. "rekan-rekan")
        changed = True
        return word

    new_text = _STUTTER_PATTERN.sub(_repl, text)
    return new_text, changed


@dataclass
class _MergedSentence:
    text_raw: str
    start_offset_ms: int
    end_offset_ms: int


def _merge_chunks_to_sentences(chunks: list[dict], gap_threshold_ms: int) -> list[_MergedSentence]:
    """Gabungkan chunk ASR granular jadi kalimat utuh.

    chunks: list of {"text","duration","offset","lang"} sesuai transcript.json asli.
    """
    sentences: list[_MergedSentence] = []
    buffer_texts: list[str] = []
    buffer_start = None
    prev_end = None

    for chunk in chunks:
        text = chunk["text"]
        start = chunk["offset"]
        end = chunk["offset"] + chunk["duration"]

        gap_too_large = prev_end is not None and (start - prev_end) > gap_threshold_ms
        if gap_too_large and buffer_texts:
            sentences.append(
                _MergedSentence(
                    text_raw=collapse_whitespace(" ".join(buffer_texts)),
                    start_offset_ms=buffer_start,
                    end_offset_ms=prev_end,
                )
            )
            buffer_texts = []
            buffer_start = None

        if buffer_start is None:
            buffer_start = start
        buffer_texts.append(text)
        prev_end = end

        if text.rstrip().endswith(_SENTENCE_END_CHARS):
            sentences.append(
                _MergedSentence(
                    text_raw=collapse_whitespace(" ".join(buffer_texts)),
                    start_offset_ms=buffer_start,
                    end_offset_ms=prev_end,
                )
            )
            buffer_texts = []
            buffer_start = None

    if buffer_texts:
        sentences.append(
            _MergedSentence(
                text_raw=collapse_whitespace(" ".join(buffer_texts)),
                start_offset_ms=buffer_start,
                end_offset_ms=prev_end,
            )
        )

    return sentences


def _strip_edge_fillers(text: str, fillers: list[str]) -> str:
    """Hapus filler yang berdiri sendiri di awal/akhir kalimat (dengan atau
    tanpa koma mengikuti), tanpa menyentuh filler di tengah kalimat.

    Tanda baca akhir kalimat (. ! ?) pada token filler terakhir dipertahankan
    dan dipindah ke kata sebelumnya, supaya kalimat hasil tidak kehilangan
    penanda akhir (mis. "...ukur ya." -> "...ukur.", bukan "...ukur").
    """
    filler_set = {f.lower() for f in fillers}
    words = text.split(" ")
    if not words:
        return text

    def _is_filler_token(token: str) -> bool:
        return token.strip(",.!?").lower() in filler_set

    while words and _is_filler_token(words[0]):
        words.pop(0)

    trailing_punct = ""
    while words and _is_filler_token(words[-1]):
        stripped = words[-1].strip(",.!?")
        punct = words[-1][len(stripped):]
        if punct and not trailing_punct:
            trailing_punct = punct
        words.pop()

    if trailing_punct and words and not words[-1].endswith((".", "!", "?")):
        words[-1] = words[-1] + trailing_punct

    result = " ".join(words)
    return result[0].upper() + result[1:] if result else result


def _find_near_duplicates(sentences: list[str], threshold: float) -> dict[int, int]:
    """Kembalikan mapping {index_duplikat: index_original} untuk kalimat yang
    similarity-nya >= threshold dengan kalimat sebelumnya yang sudah diproses.

    Menggunakan difflib (stdlib) - cukup untuk dataset per-video yang jumlah
    kalimatnya kecil-menengah (puluhan-ratusan). Untuk skala jauh lebih besar,
    ganti dengan pendekatan embedding-based tanpa mengubah kontrak fungsi ini.
    """
    duplicate_map: dict[int, int] = {}
    normalized = [s.lower().strip() for s in sentences]

    for i in range(len(normalized)):
        if i in duplicate_map:
            continue
        for j in range(i):
            if j in duplicate_map:
                continue
            ratio = difflib.SequenceMatcher(None, normalized[i], normalized[j]).ratio()
            if ratio >= threshold:
                duplicate_map[i] = j
                break
    return duplicate_map


class TranscriptCleaner(Cleaner):
    stage_name = "transcript"

    def clean(self, raw_data: list[dict], dataset_id: str):
        report = CleaningReport(stage_name=self.stage_name)

        gap_threshold = self.config.get("sentence_merge_gap_ms", 1500)
        merged = _merge_chunks_to_sentences(raw_data, gap_threshold)
        report.items_processed = len(merged)

        texts_raw = [m.text_raw for m in merged]

        dup_map = {}
        if self.config.get("dedup_similarity_threshold"):
            dup_map = _find_near_duplicates(
                texts_raw, self.config["dedup_similarity_threshold"]
            )
            report.duplicates_flagged = len(dup_map)

        fillers = self.dictionaries.get("filler_words", {}).get("standalone_fillers", [])
        brand_map = self.dictionaries.get("brand_corrections", {})
        term_map = self.dictionaries.get("terminology_map", {})
        flagging_patterns = self.dictionaries.get("flagging_patterns", {})

        results = []
        for idx, m in enumerate(merged):
            text = m.text_raw
            modified = False
            dict_corrected = False

            if self.config.get("remove_fillers", True):
                new_text = _strip_edge_fillers(text, fillers)
                modified = modified or (new_text != text)
                text = new_text

            if self.config.get("collapse_stutter", True):
                new_text, changed = _collapse_stutter(text, {f.lower() for f in fillers})
                modified = modified or changed
                text = new_text

            if self.config.get("apply_brand_correction", True):
                text, changed = apply_dictionary(text, brand_map)
                modified = modified or changed
                dict_corrected = dict_corrected or changed

            if self.config.get("apply_terminology_correction", True):
                text, changed = apply_dictionary(text, term_map)
                modified = modified or changed
                dict_corrected = dict_corrected or changed

            if self.config.get("normalize_numbers", True):
                new_text = normalize_decimal_numbers(text)
                modified = modified or (new_text != text)
                text = new_text

            if modified:
                report.items_modified += 1

            flags: list[str] = []
            if self.config.get("enable_flagging", True):
                flags = detect_flags(text, flagging_patterns, dict_corrected)
                if flags:
                    report.flagged_for_review += 1

            results.append(
                {
                    "sentence_id": f"s{idx + 1:04d}",
                    "text_raw": m.text_raw,
                    "text_clean": text,
                    "start_offset_ms": m.start_offset_ms,
                    "end_offset_ms": m.end_offset_ms,
                    "is_duplicate_of": (
                        f"s{dup_map[idx] + 1:04d}" if idx in dup_map else None
                    ),
                    "flags": flags,
                    "needs_review": len(flags) > 0,
                }
            )

        return results, report
