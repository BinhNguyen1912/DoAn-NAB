"""Test `src/drift_samples.py` (ticket 15): ghi từng mẫu drift + các phép phân tích thuần.

Khoá bằng **số literal tính tay** (CODING_STANDARDS) — không tính lại kỳ vọng bằng chính code đang
test. Riêng `rolling_p05` thì so với `numpy.percentile` trên đúng cửa sổ đó (cùng định nghĩa với
`_apply_drift_locked` của phiên live, thứ mà CSV phải tái lập được).
"""

import json

import numpy as np
import pytest

from src.drift_samples import (
    CSV_HEADER,
    DriftSampleLog,
    detect_latency,
    flag_rate,
    read_samples,
    rolling_p05,
    static_control,
    summarize,
)


def _rows(values, empties=None):
    """Dòng CSV giả: chỉ `drift_iou` + `empty` là có nghĩa cho phân tích."""
    empties = empties or [False] * len(values)
    return [{"drift_iou": value, "empty": empty} for value, empty in zip(values, empties)]


class TestGhiCsv:
    def test_moi_mau_mot_dong_va_o_trong_la_chua_do(self, tmp_path):
        """Ghi 2 mẫu: 1 đủ số, 1 thiếu `vos_ms`/`bbox` ⇒ dòng đó TRỐNG ô, đọc lại là `None`."""
        log = DriftSampleLog(tmp_path / "sub" / "drift_samples.csv")
        log.write(frame_idx=10, seq=3, vos_ms=131.5, empty=False, drift_iou=0.875,
                  bbox=(1, 2, 30, 40))
        log.write(frame_idx=11, seq=4, vos_ms=None, empty=None, drift_iou=None, bbox=None)
        log.close()

        assert log.path.read_text(encoding="utf-8").splitlines()[0] == ",".join(CSV_HEADER)
        rows = read_samples(log.path)
        assert len(rows) == 2
        assert rows[0]["frame_idx"] == 10 and rows[0]["seq"] == 3
        assert rows[0]["vos_ms"] == 131.5 and rows[0]["empty"] is False
        assert rows[0]["drift_iou"] == 0.875 and rows[0]["bbox"] == (1, 2, 30, 40)
        # Ô trống ⇒ None. Đọc thành 0/False sẽ biến "chưa đo" thành một khẳng định (AGENTS §6).
        assert rows[1]["vos_ms"] is None and rows[1]["empty"] is None
        assert rows[1]["drift_iou"] is None and rows[1]["bbox"] == (None, None, None, None)

    def test_chua_ghi_gi_thi_khong_sinh_file(self, tmp_path):
        """Phiên tắt LK (`vos_every=1`) không đo mẫu ⇒ KHÔNG được để lại CSV chỉ có header.

        File rỗng có header rất dễ bị đọc thành "đã đo, 0 mẫu" trong lúc sự thật là "không đo".
        """
        log = DriftSampleLog(tmp_path / "drift_samples.csv")
        log.close()
        assert not log.path.exists()

    def test_dem_so_dong_va_ghi_tu_hai_luong(self, tmp_path):
        """Ghi từ 2 luồng (VOS + luồng chính) ⇒ không mất dòng, `n_rows` khớp số dòng dữ liệu."""
        import threading

        log = DriftSampleLog(tmp_path / "drift_samples.csv")

        def ghi(lô, seq_bắt_đầu):
            for i in range(lô):
                log.write(frame_idx=i, seq=seq_bắt_đầu + i, vos_ms=100.0, empty=False,
                          drift_iou=1.0, bbox=(0, 0, 10, 10))

        threads = [threading.Thread(target=ghi, args=(50, k * 100)) for k in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        log.close()

        assert log.n_rows == 100
        assert len(read_samples(log.path)) == 100


class TestRollingP05:
    def test_none_cho_toi_khi_du_cua_so(self):
        series = rolling_p05([0.9] * 5, window=3)
        assert series[:2] == [None, None]
        assert series[2] == pytest.approx(0.9)

    def test_khop_dinh_nghia_percentile_noi_suy_tuyen_tinh(self):
        """Cửa sổ 4 mẫu [0,4; 0,6; 0,8; 1,0]: chỉ số p05 = 0,05 × (4-1) = 0,15

        ⇒ 0,4 + 0,15 × (0,6 - 0,4) = **0,43** (tính tay). Phải khớp `np.percentile` — cùng định
        nghĩa với `drift_iou_p05` trong `status.json`, nếu không CSV sẽ "giải thích" sai con số đã
        công bố.
        """
        values = [0.4, 0.6, 0.8, 1.0]
        series = rolling_p05(values, window=4)
        assert series[:3] == [None, None, None]
        assert series[3] == pytest.approx(0.43)
        assert series[3] == round(float(np.percentile(values, 5)), 4)

    def test_cua_so_truot_thay_duoi_xau(self):
        """Thêm một mẫu 0,0 vào cuối: cửa sổ mới [0,6; 0,8; 1,0; 0,0] sắp xếp [0; 0,6; 0,8; 1,0]

        ⇒ 0 + 0,15 × (0,6 - 0) = **0,09**. Đúng cơ chế khiến p05 phản ứng nhanh với một cú hỏng
        hoàn toàn nhưng chậm khi chỉ lệch nhẹ.
        """
        series = rolling_p05([0.4, 0.6, 0.8, 1.0, 0.0], window=4)
        assert series[4] == pytest.approx(0.09)


class TestTiLeBaoVaDoTre:
    def test_ti_le_bao_tren_clip_khoe(self):
        """30 mẫu cùng 0,9 với cửa sổ 10 ⇒ 21 cửa sổ, p05 = 0,9 ⇒ báo 0/21 = 0,0."""
        result = flag_rate([0.9] * 30, threshold=0.7, window=10)
        assert result["n_cua_so"] == 21
        assert result["n_bao"] == 0
        assert result["ti_le_bao"] == 0.0

    def test_ti_le_bao_none_khi_chua_du_cua_so(self):
        """9 mẫu với cửa sổ 10 ⇒ 0 cửa sổ ⇒ `None` (chưa đo), KHÔNG phải 0 %.

        Bẫy thật của repo: "0/None ≠ đã đo" (AGENTS §6) — 0 % báo oan là một kết luận, không được
        suy ra từ việc chưa có cửa sổ nào.
        """
        result = flag_rate([0.1] * 9, threshold=0.7, window=10)
        assert result["n_cua_so"] == 0
        assert result["ti_le_bao"] is None

    def test_bat_duoc_khi_p05_tut_duoi_nguong(self):
        """10 mẫu 0,9 rồi 10 mẫu 0,0, cửa sổ 5 ⇒ 16 cửa sổ.

        Cửa sổ kết thúc ở chỉ số 9 toàn 0,9 ⇒ p05 = 0,9 (không báo). Từ chỉ số 10 (một phần tử
        0,0): sắp xếp [0; 0,9; 0,9; 0,9; 0,9] ⇒ 0 + 0,2 × 0,9 = 0,18 < 0,3 ⇒ báo. Vậy **10/16**
        cửa sổ báo (chỉ số 10..19), tức 0,625.
        """
        result = flag_rate([0.9] * 10 + [0.0] * 10, threshold=0.3, window=5)
        assert result["n_cua_so"] == 16
        assert result["n_bao"] == 10
        assert result["ti_le_bao"] == pytest.approx(0.625)

    def test_do_tre_phat_hien_tinh_tay(self):
        """Cửa sổ 4, mẫu xấu đầu tiên ở chỉ số 2 (0,2 < 0,5).

        Dãy drift: [0,9; 0,9; 0,2; 0,2; 0,2; 0,2]. Cửa sổ ĐẦY ĐẦU TIÊN kết thúc ở chỉ số 3 =
        [0,9; 0,9; 0,2; 0,2] ⇒ p05 = 0,2 + 0,15 × 0 = **0,2** < 0,3 ⇒ phát hiện ngay tại mẫu thứ
        3, tức **1 mẫu** sau mẫu xấu đầu (3 - 2).
        """
        rows = _rows([0.9, 0.9, 0.2, 0.2, 0.2, 0.2])
        result = detect_latency(rows, bad=0.5, flag=0.3, window=4)
        assert result["mau_xau_dau"] == 2
        assert result["phat_hien_sau_mau"] == 1
        assert result["p05_luc_phat_hien"] == pytest.approx(0.2)

    def test_mot_mau_xau_le_te_chua_du_lam_p05_tut(self):
        """Một mẫu 0,2 giữa toàn 0,9 ⇒ p05 của cửa sổ = 0,2 + 0,15 × 0,7 = **0,305** ≥ 0,3.

        Đây là biểu hiện của độ trễ bất đối xứng cần đo: một cú lệch đơn lẻ KHÔNG đủ làm cờ bật.
        """
        rows = _rows([0.9, 0.9, 0.2, 0.9, 0.9, 0.9, 0.9, 0.9])
        result = detect_latency(rows, bad=0.5, flag=0.3, window=4)
        assert result["mau_xau_dau"] == 2
        assert result["phat_hien_sau_mau"] is None
        assert result["p05_luc_phat_hien"] is None

    def test_clip_khong_co_mau_xau_thi_khong_phai_phat_hien_sau_0_mau(self):
        result = detect_latency(_rows([0.9] * 20), bad=0.5, flag=0.3, window=5)
        assert result["mau_xau_dau"] is None
        assert result["phat_hien_sau_mau"] is None


class TestDoiChungCanhTinh:
    def test_canh_tinh_dat_khi_drift_gan_1(self):
        result = static_control(_rows([1.0] * 25))
        assert result["n"] == 25
        assert result["drift_iou_mean"] == 1.0
        assert result["dat"] is True
        assert result["ly_do"] == []
        assert result["ghi_chu"] == []

    def test_canh_tinh_khong_dat_khi_thieu_mau(self):
        result = static_control(_rows([1.0] * 5))
        assert result["drift_iou_p05"] is None      # chưa đủ mẫu ⇒ chưa công bố phân vị
        assert result["dat"] is False
        assert "chưa đủ" in result["ly_do"][0]

    def test_mean_dat_nhung_p05_thap_thi_van_dat_va_co_ghi_chu(self):
        """Số ĐO THẬT 13-11 (cảnh tĩnh, 357 dòng): mean 0,9955 / p05 0,9885.

        Tiêu chí của ticket là `drift_iou >= 0,99` trên **mean** ⇒ ĐẠT. `p05` dưới ngưỡng do làm
        tròn toạ độ nguyên của LK — phải được ghi chú chứ không âm thầm bỏ qua.
        """
        rows = _rows([0.9955] * 340 + [0.985] * 40)
        result = static_control(rows)
        assert result["drift_iou_mean"] == pytest.approx(0.995, abs=1e-3)
        assert result["drift_iou_p05"] < 0.99
        assert result["dat"] is True
        assert result["ly_do"] == []
        assert "làm tròn toạ độ nguyên" in result["ghi_chu"][0]

    def test_canh_tinh_khong_dat_khi_drift_tut_that(self):
        """Cảnh tĩnh mà drift thấp ⇒ lỗi SO LỆCH CẶP FRAME (bookkeeping), không phải "LK kém"."""
        rows = _rows([1.0] * 20 + [0.5] * 20)
        result = static_control(rows)
        assert result["dat"] is False
        assert "nghi so lệch cặp frame" in result["ly_do"][0]


class TestSummarize:
    def test_tom_tat_giu_encoding_chua_do(self):
        """`empty_frac` chỉ tính trên dòng CÓ `empty`; thiếu hết ⇒ None (không phải 0,0)."""
        result = summarize([{"drift_iou": None, "empty": None}] * 3)
        assert result["n_dong"] == 3
        assert result["n_mau_drift"] == 0
        assert result["empty_frac"] is None
        assert result["drift_iou_mean"] is None
        assert result["drift_iou_p05"] is None
        assert result["bao_dong_070"]["ti_le_bao"] is None
        assert result["phat_hien"]["phat_hien_sau_mau"] is None


class TestPhanTichFile:
    """`scripts/analyze_drift_samples.py` — đọc CSV + `.meta.json` bên cạnh thành số của báo cáo."""

    def _viet(self, path, values, meta=None):
        lines = [",".join(CSV_HEADER)]
        for index, value in enumerate(values):
            lines.append(f"{index},{index + 1},120.0,0,{value:.4f},1,2,30,40")
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        if meta is not None:
            path.with_name(path.name.replace(".csv", ".meta.json")).write_text(
                json.dumps(meta), encoding="utf-8")

    def test_doc_duoc_meta_va_tinh_bao_dong(self, tmp_path, monkeypatch):
        import scripts.analyze_drift_samples as analyze

        monkeypatch.setattr(analyze, "_REPO_ROOT", tmp_path)
        csv = tmp_path / "drift_samples_binh1_2026-11-12_1430.csv"
        self._viet(csv, [0.9] * 10 + [0.0] * 10,
                   meta={"git_rev": "abc1234", "git_dirty_code": False,
                         "device_worker_log": "cpu", "thiet_lap": {"vos_every": 3}})

        result = analyze.analyze_file(csv, window=5, static=False)

        assert result["co_meta"] is True
        assert result["git_rev"] == "abc1234" and result["git_dirty_code"] is False
        assert result["n_mau_drift"] == 20
        assert result["drift_iou_p05"] == 0.0
        # Cửa sổ 5: 16 cửa sổ, 10 cửa sổ báo (0,625) — cùng literal như test của `flag_rate`.
        assert result["bao_dong_070"]["n_cua_so"] == 16
        assert result["bao_dong_070"]["ti_le_bao"] == pytest.approx(0.625)
        assert "doi_chung_canh_tinh" not in result          # chỉ tính khi được chỉ định là cảnh tĩnh

    def test_file_canh_tinh_duoc_cham_bang_doi_chung(self, tmp_path, monkeypatch):
        import scripts.analyze_drift_samples as analyze

        monkeypatch.setattr(analyze, "_REPO_ROOT", tmp_path)
        csv = tmp_path / "drift_samples_tinh_2026-11-12_1430.csv"
        self._viet(csv, [1.0] * 25)

        result = analyze.analyze_file(csv, window=5, static=True)

        assert result["co_meta"] is False                   # không có `.meta.json` ⇒ nói thẳng
        assert result["doi_chung_canh_tinh"]["dat"] is True
        assert result["doi_chung_canh_tinh"]["drift_iou_mean"] == 1.0
