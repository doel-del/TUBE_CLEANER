"""
dataset_io.py

Tanggung jawab tunggal: operasi baca file mentah & tulis file hasil clean,
termasuk mirroring struktur folder raw/ -> clean/.

Modul ini tidak melakukan transformasi teks apa pun (itu tugas cleaners/*.py).
Dipisah dari manifest_loader agar path-resolution (manifest) dan
read/write-mechanics (I/O) bisa berubah independen.
"""

from __future__ import annotations

import json
from pathlib import Path

from core.manifest_loader import DatasetRef


def read_json(path: Path):
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def resolve_clean_dir(dataset_dir: Path, raw_root: Path, clean_root: Path) -> Path:
    """Hitung path folder output di clean/ yang mirror posisi dataset_dir di raw/.

    Contoh:
        raw_root   = D:/TubescrapeData
        clean_root = D:/TubescrapeData_clean
        dataset_dir= D:/TubescrapeData/Power Tools/Bor Cordless/Lucid LD60/Osx1WI6buDw - ...
        -> hasil   = D:/TubescrapeData_clean/Power Tools/Bor Cordless/Lucid LD60/Osx1WI6buDw - ...
    """
    relative = dataset_dir.relative_to(raw_root)
    return clean_root / relative


def write_json(path: Path, data) -> None:
    """Tulis JSON hasil clean. Membuat parent directory jika belum ada."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_raw_dataset(ref: DatasetRef) -> dict:
    """Muat seluruh file mentah satu dataset ke memori sebagai dict.

    Mengembalikan dict dengan key: metadata, comments, transcript
    (semua dari varian .json, karena .txt hanya representasi tampilan
    yang diturunkan dari .json - lihat catatan desain awal).
    """
    return {
        "metadata": read_json(ref.metadata_path),
        "comments": read_json(ref.comments_json_path),
        "transcript": read_json(ref.transcript_json_path),
    }
