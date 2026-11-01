"""Test provenance file `{tag}_run_info.json` — lần đo phải TỰ GIẢI THÍCH được.

Vì sao có file này: lần đo `fast_1029-212010` (234 frame, mất dấu từ f58 đến hết, 0 nhận lại)
KHÔNG phân biệt được là "vật rời khung rồi không quay lại" (hành vi đúng) hay "re-ID lỗi"
(bug) — vì CSV không ghi nguồn/config/git. `.gitignore` đã whitelist `!data/*_run_info.json`
nhưng chỉ `scripts/colab_run_all.py` ghi file này, đường local `./run fast` thì không.

Seam test:
- `run_info_path_for(...)`  — suy đường dẫn từ file metrics (pure, quyết định tên file).
- `write_run_info(path, ...)` — ghi JSON, tự tạo thư mục cha, tự thêm `timestamp`.
"""
import datetime
import json

from src.metrics_logger import run_info_path_for, write_run_info


class TestRunInfoDuongDan:
    """X_summary.json / X_metrics.csv → X_run_info.json (khớp pattern .gitignore)."""

    def test_tu_summary(self):
        assert run_info_path_for(metrics_summary="data/fast_1_summary.json") \
            == "data/fast_1_run_info.json"

    def test_tu_csv_khi_khong_co_summary(self):
        assert run_info_path_for(metrics_csv="data/fast_1_metrics.csv") \
            == "data/fast_1_run_info.json"

    def test_uu_tien_summary_hon_csv(self):
        assert run_info_path_for(metrics_csv="data/a_metrics.csv",
                                 metrics_summary="data/b_summary.json") \
            == "data/b_run_info.json"

    def test_khong_co_file_nao_tra_none(self):
        assert run_info_path_for() is None

    def test_ten_khac_van_thay_hau_to(self):
        # tên không theo quy ước: bỏ đuôi, gắn _run_info.json
        assert run_info_path_for(metrics_csv="data/metrics.csv") == "data/metrics_run_info.json"


class TestGhiRunInfo:
    """`write_run_info` ghi JSON round-trip + tự tạo thư mục cha + timestamp đọc được."""

    def test_round_trip_va_tu_tao_thu_muc(self, tmp_path):
        p = tmp_path / "nested" / "fast_1_run_info.json"      # thư mục cha CHƯA có
        out = write_run_info(str(p), source="0", image_size=256, git_rev="abc1234")

        assert out == str(p)
        assert p.is_file()
        d = json.loads(p.read_text(encoding="utf-8"))
        assert d["source"] == "0"
        assert d["image_size"] == 256
        assert d["git_rev"] == "abc1234"
        datetime.datetime.fromisoformat(d["timestamp"])        # parse được → có mốc thời gian

    def test_giu_timestamp_truyen_vao(self, tmp_path):
        p = tmp_path / "x_run_info.json"
        write_run_info(str(p), timestamp="2026-11-01T10:00:00", source="0")
        d = json.loads(p.read_text(encoding="utf-8"))
        assert d["timestamp"] == "2026-11-01T10:00:00"
