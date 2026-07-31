"""
manifest_loader.py

Tanggung jawab tunggal: membaca & memvalidasi tube_manifest.json,
lalu mengembalikan objek DatasetRef berisi path absolut ke tiap file
(metadata, comments, transcript) untuk satu dataset.

Modul ini TIDAK tahu apa-apa tentang isi/format teks di dalam file-file
tersebut - itu tanggung jawab cleaners/*.py. Manifest_loader hanya
mengurus resolusi path & validasi struktural manifest.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


REQUIRED_MANIFEST_KEYS = {"dataset", "source", "files"}
REQUIRED_FILE_KEYS = {"metadata", "comments", "transcript"}


class ManifestValidationError(Exception):
    """Dilempar saat tube_manifest.json tidak sesuai kontrak minimum."""


@dataclass(frozen=True)
class DatasetRef:
    """Referensi path lengkap untuk satu dataset video, hasil resolusi manifest."""

    dataset_id: str
    video_id: str
    dataset_dir: Path
    metadata_path: Path
    comments_json_path: Path
    comments_txt_path: Path
    transcript_json_path: Path
    transcript_txt_path: Path


def _require_keys(obj: dict, keys: set[str], context: str) -> None:
    missing = keys - obj.keys()
    if missing:
        raise ManifestValidationError(
            f"Manifest tidak lengkap di bagian '{context}': field hilang {sorted(missing)}"
        )


def load_manifest(manifest_path: Path) -> DatasetRef:
    """
    Baca satu tube_manifest.json dan kembalikan DatasetRef dengan path
    absolut ke semua file terkait, relatif terhadap folder manifest.

    Raises:
        ManifestValidationError: jika struktur manifest tidak sesuai kontrak
            atau file yang dirujuk tidak ditemukan di disk.
    """
    dataset_dir = manifest_path.parent

    with manifest_path.open("r", encoding="utf-8") as f:
        manifest = json.load(f)

    _require_keys(manifest, REQUIRED_MANIFEST_KEYS, "root")
    _require_keys(manifest["files"], REQUIRED_FILE_KEYS, "files")
    _require_keys(manifest["files"]["comments"], {"json", "text"}, "files.comments")
    _require_keys(manifest["files"]["transcript"], {"json", "text"}, "files.transcript")
    _require_keys(manifest["files"]["metadata"], {"path"}, "files.metadata")

    dataset_id = manifest["dataset"]["dataset_id"]
    video_id = manifest["source"]["video_id"]

    ref = DatasetRef(
        dataset_id=dataset_id,
        video_id=video_id,
        dataset_dir=dataset_dir,
        metadata_path=dataset_dir / manifest["files"]["metadata"]["path"],
        comments_json_path=dataset_dir / manifest["files"]["comments"]["json"],
        comments_txt_path=dataset_dir / manifest["files"]["comments"]["text"],
        transcript_json_path=dataset_dir / manifest["files"]["transcript"]["json"],
        transcript_txt_path=dataset_dir / manifest["files"]["transcript"]["text"],
    )

    _verify_files_exist(ref)
    return ref


def _verify_files_exist(ref: DatasetRef) -> None:
    """Pastikan semua file yang dirujuk manifest benar-benar ada di disk.

    Sengaja dipisah dari validasi struktur manifest supaya error message
    membedakan 'manifest salah format' vs 'file hilang di disk' -
    dua kelas masalah berbeda saat debugging dataset besar.
    """
    candidates = {
        "metadata": ref.metadata_path,
        "comments.json": ref.comments_json_path,
        "comments.txt": ref.comments_txt_path,
        "transcript.json": ref.transcript_json_path,
        "transcript.txt": ref.transcript_txt_path,
    }
    missing = [name for name, p in candidates.items() if not p.exists()]
    if missing:
        raise ManifestValidationError(
            f"Dataset '{ref.dataset_id}': file berikut dirujuk manifest tapi tidak "
            f"ditemukan di disk: {missing}"
        )


def discover_manifests(root_dir: Path) -> list[Path]:
    """Cari semua tube_manifest.json / tube.manifest.json di bawah root_dir secara rekursif.

    Mendukung kedua variasi nama file karena ditemukan inkonsistensi penamaan
    di dataset mentah (lihat catatan analisis awal).
    """
    found: list[Path] = []
    for pattern in ("tube_manifest.json", "tube.manifest.json"):
        found.extend(root_dir.rglob(pattern))
    return sorted(set(found))
