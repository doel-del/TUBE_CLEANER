"""
report_generator.py

Menulis ringkasan hasil cleaning (audit trail) ke JSON, terpisah dari
file clean/ itu sendiri. Tujuannya supaya proses review kualitas
(mis. cek berapa banyak duplicate terdeteksi, berapa koreksi diterapkan)
tidak perlu buka & diff file data yang besar.
"""

from __future__ import annotations

import json
from pathlib import Path


def write_dataset_report(output_dir: Path, dataset_id: str, reports: list[dict]) -> Path:
    report_path = output_dir / "cleaning_report.json"
    payload = {"dataset_id": dataset_id, "stages": reports}
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with report_path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return report_path


def write_batch_summary(clean_root: Path, all_reports: list[dict]) -> Path:
    """Ringkasan lintas semua dataset yang diproses dalam satu batch run."""
    summary_path = clean_root / "batch_summary.json"
    with summary_path.open("w", encoding="utf-8") as f:
        json.dump({"datasets": all_reports}, f, ensure_ascii=False, indent=2)
    return summary_path
