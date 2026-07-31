"""
main.py

CLI entrypoint TUBE CLEANER.

Usage:
    python main.py --raw-root <path_ke_TubescrapeData> --clean-root <path_output>

Alur:
1. Load config & dictionaries sekali di awal (tidak reload per dataset).
2. Discover semua tube_manifest.json di bawah raw-root (rekursif).
3. Untuk tiap dataset: load manifest -> jalankan pipeline -> tulis hasil
   clean (mirror struktur folder) + report per dataset.
4. Tulis batch_summary.json di akhir.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

from core.manifest_loader import discover_manifests, load_manifest, ManifestValidationError
from core.dataset_io import resolve_clean_dir, write_json
from core.pipeline import run_pipeline
from reports.report_generator import write_dataset_report, write_batch_summary


def load_config(config_dir: Path) -> tuple[dict, dict]:
    with (config_dir / "pipeline_config.yaml").open("r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    dictionaries = {}
    dict_dir = config_dir / "dictionaries"
    for name in ("slang_map", "brand_corrections", "terminology_map", "filler_words", "flagging_patterns"):
        path = dict_dir / f"{name}.yaml"
        with path.open("r", encoding="utf-8") as f:
            dictionaries[name] = yaml.safe_load(f) or {}

    return config, dictionaries


def process_dataset(manifest_path: Path, raw_root: Path, clean_root: Path, config, dictionaries):
    ref = load_manifest(manifest_path)
    result = run_pipeline(ref, config, dictionaries)

    clean_dir = resolve_clean_dir(ref.dataset_dir, raw_root, clean_root)
    write_json(clean_dir / "metadata.json", result["metadata"])
    write_json(clean_dir / "comments_clean.json", result["comments"])
    write_json(clean_dir / "transcript_clean.json", result["transcript"])

    if config.get("output", {}).get("write_report", True):
        write_dataset_report(clean_dir, result["dataset_id"], result["reports"])

    return {"dataset_id": result["dataset_id"], "output_dir": str(clean_dir), "reports": result["reports"]}


def main():
    parser = argparse.ArgumentParser(description="TUBE CLEANER - preprocessing layer untuk dataset TubeScrape")
    parser.add_argument("--raw-root", required=True, type=Path, help="Root folder dataset mentah (TubescrapeData/)")
    parser.add_argument("--clean-root", required=True, type=Path, help="Root folder output hasil clean")
    parser.add_argument(
        "--config-dir",
        type=Path,
        default=Path(__file__).parent / "config",
        help="Folder berisi pipeline_config.yaml & dictionaries/ (default: ./config)",
    )
    args = parser.parse_args()

    config, dictionaries = load_config(args.config_dir)
    manifests = discover_manifests(args.raw_root)

    if not manifests:
        print(f"Tidak ada tube_manifest.json ditemukan di bawah {args.raw_root}", file=sys.stderr)
        sys.exit(1)

    batch_results = []
    for manifest_path in manifests:
        try:
            result = process_dataset(manifest_path, args.raw_root, args.clean_root, config, dictionaries)
            batch_results.append(result)
            print(f"[OK] {result['dataset_id']} -> {result['output_dir']}")
        except ManifestValidationError as e:
            print(f"[SKIP] {manifest_path}: {e}", file=sys.stderr)

    write_batch_summary(args.clean_root, batch_results)
    print(f"\nSelesai. {len(batch_results)}/{len(manifests)} dataset berhasil diproses.")


if __name__ == "__main__":
    main()
