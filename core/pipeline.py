"""
pipeline.py

Orchestrator tingkat-dataset: memanggil cleaner yang relevan (comment,
transcript) untuk satu DatasetRef, lalu mengembalikan hasil clean +
report gabungan. Tidak tahu detail transformasi teks (itu di cleaners/*.py)
maupun cara file ditemukan di disk (itu di manifest_loader.py).

Menambah cleaner baru (mis. untuk metadata) = tambah satu baris di sini,
tanpa mengubah cleaner lain.
"""

from __future__ import annotations

from core.dataset_io import load_raw_dataset
from core.manifest_loader import DatasetRef
from cleaners.comment_cleaner import CommentCleaner
from cleaners.transcript_cleaner import TranscriptCleaner


def run_pipeline(ref: DatasetRef, config: dict, dictionaries: dict) -> dict:
    """Jalankan seluruh stage cleaning untuk satu dataset.

    Returns:
        dict dengan key: dataset_id, metadata (passthrough), comments (clean),
        transcript (clean), reports (list of CleaningReport.as_dict()).
    """
    raw = load_raw_dataset(ref)
    reports = []

    comment_cleaner = CommentCleaner(
        config.get("comments", {}),
        dictionaries,
        channel_name=raw["metadata"].get("channel"),
    )
    clean_comments, comment_report = comment_cleaner.clean(raw["comments"], ref.dataset_id)
    reports.append(comment_report.as_dict())

    transcript_cleaner = TranscriptCleaner(config.get("transcript", {}), dictionaries)
    clean_transcript, transcript_report = transcript_cleaner.clean(
        raw["transcript"], ref.dataset_id
    )
    reports.append(transcript_report.as_dict())

    return {
        "dataset_id": ref.dataset_id,
        "metadata": raw["metadata"],  # passthrough, sudah relatif bersih (lihat analisis awal)
        "comments": clean_comments,
        "transcript": clean_transcript,
        "reports": reports,
    }
