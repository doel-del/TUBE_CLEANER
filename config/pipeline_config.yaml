# pipeline_config.yaml
# Konfigurasi perilaku tiap stage cleaning. Tidak ada logic di sini,
# murni parameter -> supaya tuning tidak perlu ubah kode (lihat cleaners/*.py).

transcript:
  sentence_merge_gap_ms: 1500      # gap antar-chunk ASR yg masih dianggap 1 kalimat
  dedup_similarity_threshold: 0.90 # ambang similarity utk deteksi near-duplicate segmen
  remove_fillers: true
  collapse_stutter: true          # gabungkan kata terulang akibat disfluency (mis. "kan-kan" -> "kan")
  enable_flagging: true           # tandai kalimat berisiko ASR error (numerik/teknis) untuk review manual
  apply_brand_correction: true
  apply_terminology_correction: true
  normalize_numbers: true          # koma desimal id -> titik

comments:
  strip_html: true
  extract_links: true
  normalize_mentions: true         # hilangkan ZWSP & rapikan format @mention
  dedup_exact_match: true          # deteksi komentar identik persis (mis. duplicate post)
  dedup_min_length: 15             # teks lebih pendek dari ini tidak dicek dedup -
                                    # reply generik pendek ("😁", "ok") dari berbagai
                                    # author ke komentar berbeda bukan duplicate spam,
                                    # cuma kebetulan sama (ditemukan saat uji coba data nyata)
  normalize_slang: false           # default OFF -> lihat alasan di README/desain (risiko ubah makna opini)
  apply_terminology_correction: false  # default OFF, sama alasan spt slang
  keep_emoji: true                 # emoji dipertahankan di text_clean, hanya markup/ZWSP yg dibersihkan

output:
  root_dir: "clean"
  mirror_raw_structure: true
  write_report: true
