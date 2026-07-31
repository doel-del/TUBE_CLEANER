"""
base.py

Interface abstrak untuk semua cleaner. Setiap cleaner konkret
(comment_cleaner, transcript_cleaner, dst) mengimplementasikan `clean()`
dengan kontrak input/output yang konsisten, supaya pipeline.py bisa
memanggil cleaner apa pun secara seragam tanpa tahu detail internalnya.

Menambah cleaner baru (mis. untuk sumber data baru selain YouTube)
cukup subclass ini - tidak perlu ubah core/pipeline.py.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class CleaningReport:
    """Ringkasan perubahan yang dilakukan satu cleaner terhadap satu dataset.

    Dipakai reports/report_generator.py untuk audit trail - supaya setiap
    koreksi otomatis bisa ditelusuri balik, bukan black box.
    """

    stage_name: str
    items_processed: int = 0
    items_modified: int = 0
    duplicates_flagged: int = 0
    flagged_for_review: int = 0
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "stage_name": self.stage_name,
            "items_processed": self.items_processed,
            "items_modified": self.items_modified,
            "duplicates_flagged": self.duplicates_flagged,
            "flagged_for_review": self.flagged_for_review,
            "notes": self.notes,
        }


class Cleaner(ABC):
    """Kontrak dasar: terima data mentah (dict/list hasil parse JSON) + config,
    kembalikan (data_clean, CleaningReport).
    """

    stage_name: str = "base"

    def __init__(self, config: dict, dictionaries: dict):
        """
        Args:
            config: subset pipeline_config.yaml khusus stage ini
                (mis. config['comments'] atau config['transcript']).
            dictionaries: dict berisi semua dictionary yang sudah di-load
                (slang_map, brand_corrections, terminology_map, filler_words).
        """
        self.config = config
        self.dictionaries = dictionaries

    @abstractmethod
    def clean(self, raw_data, dataset_id: str) -> tuple:
        """Bersihkan raw_data, kembalikan (clean_data, CleaningReport)."""
        raise NotImplementedError
