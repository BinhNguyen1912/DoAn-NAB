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
    MIN_SAMPLES,
    WINDOW,
    DriftSampleLog,
    low_p05_low_empty,
    detect_latency,
    flag_rate,
    phan_vi,
    read_samples,
    rolling_p05,
    static_control,
    summarize,
    tach_theo_cac_khung,
    tach_theo_khung,
    thong_ke_mau,
)
from src.drift_samples import _opt_bool


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
        self._viet(csv, [0.9] * 30 + [0.0] * 10,
                   meta={"git_rev": "abc1234", "git_dirty_code": False,
                         "device_worker_log": "cpu", "thiet_lap": {"vos_every": 3}})

        result = analyze.analyze_file(csv, window=5, static=False)

        assert result["co_meta"] is True
        assert result["git_rev"] == "abc1234" and result["git_dirty_code"] is False
        assert result["n_mau_drift"] == 40
        # 30 mẫu 0,9 rồi 10 mẫu 0,0 ⇒ p05 toàn dãy = 0,0 (n = 40 >= 30 nên được công bố).
        assert result["drift_iou_p05"] == 0.0
        # Cửa sổ 5: 36 cửa sổ, cửa sổ kết thúc ở chỉ số 30..39 chứa đủ số 0 ⇒ 10 cửa sổ báo 0,70.
        assert result["bao_dong_070"]["n_cua_so"] == 36
        assert result["bao_dong_070"]["n_bao"] == 10
        assert result["bao_dong_070"]["ti_le_bao"] == pytest.approx(0.278, abs=5e-4)
        assert "doi_chung_canh_tinh" not in result          # chỉ tính khi được chỉ định là cảnh tĩnh
        assert "theo_cua_so" not in result                  # chỉ tính khi có `windows`

    def test_quet_cua_so_cho_thay_doi_lai_do_tre(self, tmp_path, monkeypatch):
        """Độ trễ phát hiện xấp xỉ **bằng độ dài cửa sổ** ⇒ quét cửa sổ mới thấy đánh đổi.

        Dãy 20 mẫu 0,9 rồi 20 mẫu 0,0 ⇒ mẫu xấu đầu ở chỉ số 20.
          - Cửa sổ 5: cửa sổ [16..20] = [0,9; 0,9; 0,9; 0,9; 0,0] ⇒ p05 = 0 + 0,2 × 0,9 = 0,18 < 0,3
            ⇒ báo NGAY tại mẫu xấu (0 mẫu trễ).
          - Cửa sổ 10: cửa sổ [11..20] = [0,9 × 9; 0,0] ⇒ p05 = 0 + 0,45 × 0,9 = 0,405 ≥ 0,3 (chưa
            báo); cửa sổ [12..21] có hai số 0 ⇒ p05 = 0,0 ⇒ báo sau **1** mẫu.
        ⇒ cửa sổ càng dài thì phát hiện càng trễ — đúng thứ phải quét mới thấy.
        """
        import scripts.analyze_drift_samples as analyze

        monkeypatch.setattr(analyze, "_REPO_ROOT", tmp_path)
        csv = tmp_path / "drift_samples_binh2_2026-11-13_1430.csv"
        self._viet(csv, [0.9] * 20 + [0.0] * 20)

        result = analyze.analyze_file(csv, window=5, windows=[5, 10])

        theo = result["theo_cua_so"]
        assert set(theo) == {"5", "10"}
        # p05 toàn dãy KHÔNG được nhân bản vào từng cửa sổ (gây hiểu sai "p05 không phụ thuộc W")
        assert "drift_iou_p05" not in theo["5"]
        # mẫu xấu đầu = chỉ số 20 ⇒ cửa sổ 5 chưa kín cho tới 24, cửa sổ 10 tới 29
        assert theo["5"]["phat_hien"]["phat_hien_sau_mau"] == 0
        assert theo["10"]["phat_hien"]["phat_hien_sau_mau"] == 1
        assert theo["5"]["bao_dong_030"]["ti_le_bao"] <= theo["10"]["bao_dong_030"]["ti_le_bao"]

    def test_in_dieu_kien_ticket_14_theo_khung_ba_trang_thai(self, tmp_path, monkeypatch, capsys):
        """Lệnh phải in được ĐIỀU KIỆN TICKET 14 **theo khung** — cổng "CHƯA ĐO" ≠ "không đạt".

        Số công bố ở phụ lục báo cáo ("p05 trong khung = 0,000, n = 60") trước 19-11 không tái lập
        được bằng công cụ nào; test này khoá cả con số **và** nhãn 3 trạng thái, vì repo đã 3 lần
        dính "cổng danh nghĩa" (assert chỉ khớp chữ luôn được in ra).
        """
        import scripts.analyze_drift_samples as analyze

        monkeypatch.setattr(analyze, "_REPO_ROOT", tmp_path)
        # 40 mẫu TRONG khung (0:39): xen kẽ 0,0 và 0,9 ⇒ p05 = 0; 5 mẫu NGOÀI khung đều rỗng.
        lines = [",".join(CSV_HEADER)]
        for i in range(40):
            lines.append(f"{i},{i + 1},120.0,0,{(0.0 if i % 8 == 0 else 0.9):.4f},1,2,30,40")
        for i in range(5):
            lines.append(f"{500 + i},{100 + i},120.0,1,,1,2,30,40")
        csv = tmp_path / "drift_samples_binh1_2026-11-19_0900.csv"
        csv.write_text("\n".join(lines) + "\n", encoding="utf-8")

        monkeypatch.setattr("sys.argv", ["analyze_drift_samples.py", "--frame-window", "0:39", str(csv)])
        assert analyze.main() == 0
        out = capsys.readouterr().out

        assert "trong n=40 rỗng=0.0 p05=0.0 (n_drift=40)" in out
        assert "điều kiện ticket 14 ở trong_khung: ĐẠT" in out
        # NGOÀI khung: 5 mẫu rỗng, 0 mẫu drift ⇒ n=0 < 30 ⇒ CHƯA ĐO, KHÔNG được in "không đạt"
        assert "ở ngoai_khung: CHƯA ĐO" in out
        assert "ở ngoai_khung: không đạt" not in out

    def test_file_canh_tinh_duoc_cham_bang_doi_chung(self, tmp_path, monkeypatch):
        import scripts.analyze_drift_samples as analyze

        monkeypatch.setattr(analyze, "_REPO_ROOT", tmp_path)
        csv = tmp_path / "drift_samples_tinh_2026-11-12_1430.csv"
        self._viet(csv, [1.0] * 25)

        result = analyze.analyze_file(csv, window=5, static=True)

        assert result["co_meta"] is False                   # không có `.meta.json` ⇒ nói thẳng
        assert result["doi_chung_canh_tinh"]["dat"] is True
        assert result["doi_chung_canh_tinh"]["drift_iou_mean"] == 1.0


class TestCuaSoP05ThapVaEmptyThap:
    """Điều kiện tiên quyết của ticket 14 — phải đếm được bằng code đã commit, không tính tay."""

    def test_cua_so_rong_nhieu_thi_khong_phai_bang_chung_lk_troi(self):
        """p05 thấp + mask rỗng cao ⇒ KHÔNG thoả điều kiện (cờ sẽ là bản sao của `empty_frac`)."""
        rows = []
        for i in range(40):
            if i % 2:                      # 50 % lần VOS trả mask rỗng (không có điểm drift)
                rows.append({"drift_iou": None, "empty": True})
            else:
                rows.append({"drift_iou": 0.0, "empty": False})
        result = low_p05_low_empty(rows, window=10, min_measured=5)
        assert result["n_cua_so_du_mau"] == 31
        assert result["n_p05_thap"] == 31
        assert result["n_p05_thap_va_empty_thap"] == 0
        assert result["co_dieu_kien_ticket_14"] is False

    def test_cua_so_p05_thap_ma_khong_rong_thi_thoa_dieu_kien(self):
        """Đúng ca cần tìm: LK trôi thật trong khi model vẫn thấy vật (mask không rỗng)."""
        rows = [{"drift_iou": 0.1, "empty": False} for _ in range(40)]
        result = low_p05_low_empty(rows, window=10, min_measured=5)
        assert result["n_p05_thap"] == 31
        assert result["n_p05_thap_va_empty_thap"] == 31
        assert result["co_dieu_kien_ticket_14"] is True

    def test_cua_so_qua_it_mau_do_duoc_thi_khong_tinh(self):
        """Toàn mask rỗng ⇒ p05 của 0 mẫu: bỏ cửa sổ, và kết luận là **None** (chưa đo).

        `False` ở đây sẽ là một khẳng định ("đã đo, không có cửa sổ nào thoả") trong khi sự thật là
        không có mẫu nào để đo — đúng bẫy `0/None ≠ đã đo` (AGENTS §6, review vòng 2 P2).
        """
        rows = [{"drift_iou": None, "empty": True} for _ in range(40)]
        result = low_p05_low_empty(rows, window=10, min_measured=5)
        assert result["n_cua_so_du_mau"] == 0
        assert result["co_dieu_kien_ticket_14"] is None

    def test_o_empty_trong_khong_bi_dem_thanh_khong_rong(self):
        """Cột `empty` trống = CHƯA ĐO ⇒ không được tính là "không rỗng" (nếu không sẽ thoả điều
        kiện ticket 14 bằng dữ liệu chưa đo)."""
        rows = [{"drift_iou": 0.1, "empty": None} for _ in range(40)]
        result = low_p05_low_empty(rows, window=10, min_measured=5)
        assert result["n_cua_so_du_mau"] == 0
        assert result["co_dieu_kien_ticket_14"] is None

    def test_min_mau_do_duoc_suy_tu_cua_so(self):
        """Cửa sổ 20 mẫu: ngưỡng mẫu đo được là 10 (window//2), KHÔNG phải 100 của `WINDOW`.

        Trước khi sửa, `--window 20` cho 0 cửa sổ một cách im lặng ⇒ người đọc tưởng "không có
        cửa sổ nào thoả" thay vì "chưa đo được".
        """
        rows = [{"drift_iou": 0.05, "empty": False} for _ in range(40)]
        result = low_p05_low_empty(rows, window=20)
        assert result["min_mau_do_duoc"] == 10
        assert result["n_cua_so_du_mau"] == 21          # 40 - 20 + 1
        assert result["co_dieu_kien_ticket_14"] is True


class TestPhanViCongBoPhanVi:
    """Ticket #23: cửa DUY NHẤT để công bố `*_p05` (5 / 20 / 30 trước đây).

    Với n nhỏ, phân vị 5 % **chính là** min ⇒ công bố nó thành "p05" là nói dối về độ tin cậy.
    """

    def test_duoi_nguong_thi_None(self):
        assert phan_vi([0.9] * (MIN_SAMPLES - 1)) is None

    def test_du_nguong_thi_cong_bo(self):
        assert phan_vi([0.9] * MIN_SAMPLES) == pytest.approx(0.9)

    def test_mang_rong_va_mot_mau_khong_bia_so(self):
        assert phan_vi([]) is None
        assert phan_vi([0.7]) is None          # n = 1 ⇒ "p05" là chính mẫu đó, không phải phân vị

    def test_gia_tri_hong_nan_inf_thi_bao_loi(self):
        """`inf` không được lọt thành p05: `json.dumps` ghi `Infinity` ⇒ `JSON.parse` của JS chết.

        `None` cũng không được: nó trộn "số đo hỏng" vào "chưa công bố" (P3, review độc lập 17-11).
        """
        for hong in (float("inf"), float("nan")):
            with pytest.raises(ValueError, match="nan/inf"):
                phan_vi([0.9] * (MIN_SAMPLES - 1) + [hong])

    def test_summarize_va_static_control_ghi_kem_nguong(self):
        """P2 review 17-11: `drift_iou_p05 = None` mà thiếu khoá ngưỡng thì đọc như "chưa đo"."""
        tom_tat = summarize(_rows([0.9] * 25))
        assert tom_tat["drift_iou_p05"] is None
        assert tom_tat["drift_iou_p05_nguong"] == MIN_SAMPLES
        assert tom_tat["drift_iou_p05_n"] == 25
        assert static_control(_rows([1.0] * 25))["drift_iou_p05_nguong"] == MIN_SAMPLES

    def test_tham_so_min_samples_ghi_de_khong_can_doi_hang_so(self):
        assert phan_vi([0.9] * 10, min_samples=10) == pytest.approx(0.9)

    def test_static_control_khong_ha_nguong_xuong_20(self):
        """25 mẫu: ĐẠT tiêu chí (ngưỡng 20 của ticket 15) nhưng p05 **chưa** được công bố."""
        result = static_control(_rows([1.0] * 25))
        assert result["n"] == 25 and result["dat"] is True
        assert result["drift_iou_p05"] is None


class TestKhoaCuaSoKhopPhien:
    def test_hang_so_khop_voi_phien_live(self):
        """`WINDOW`/`MIN_SAMPLES` phải bằng hằng của `src/live_tracking.py`.

        Nếu trôi khỏi nhau, dãy trong CSV sẽ "giải thích" một phân vị mà phiên tính bằng cửa sổ
        khác (hoặc công bố p05 từ 20 mẫu trong khi `status.json` từ chối công bố).
        """
        import src.live_tracking as live

        assert WINDOW == live._STAT_WINDOW
        assert MIN_SAMPLES == live._STAT_MIN_SAMPLES


class TestDongFileKhongBiXoa:
    def test_ghi_sau_khi_dong_thi_khong_xoa_file(self, tmp_path):
        """`close()` rồi còn `write()` (luồng VOS sống tới 5 s sau `join`) ⇒ KHÔNG mở lại mode `w`.

        Mở lại bằng `"w"` sẽ xoá sạch dãy mẫu đã ghi ⇒ artifact "trông hợp lệ" mà rỗng ruột.
        """
        log = DriftSampleLog(tmp_path / "drift_samples.csv")
        log.write(frame_idx=1, seq=1, vos_ms=100.0, empty=False, drift_iou=0.9, bbox=(0, 0, 5, 5))
        log.close()
        log.write(frame_idx=2, seq=2, vos_ms=100.0, empty=False, drift_iou=0.8, bbox=(0, 0, 5, 5))

        assert log.n_rows == 1                        # mẫu tới sau khi đóng bị BỎ, không ghi đè
        assert len(read_samples(log.path)) == 1

    def test_doc_lai_empty_la_chuoi_la_thi_none(self):
        """Cột `empty` chỉ nhận 1/0; chuỗi lạ ⇒ None (chưa đo), không thành False."""
        assert _opt_bool("1") is True and _opt_bool("0") is False
        assert _opt_bool("True") is None and _opt_bool("") is None


class TestTachTheoKhung:
    """`tach_theo_khung` — tách "vật còn trong khung" khỏi "vật đã rời khung" (đo 14-11).

    Lý do tồn tại: `binh1` cất chai từ frame ~115, nên `empty_frac` cả phiên = 35–36 % trong khi
    **0,0 %** khi vật còn trong khung. Không tách thì con số bị đọc thành "model mất dấu".
    Số kỳ vọng dưới đây tính tay từ 6 dòng mẫu:
      frame 0,10,20 (trong khung): empty 0,0,0 · drift 0,9,0,8,0,7
      frame 200,210,220 (ngoài)  : empty 1,1,0 · drift 0,4,None,0,2
    """

    @staticmethod
    def _mau():
        return [
            {"frame_idx": 0, "empty": False, "drift_iou": 0.9},
            {"frame_idx": 10, "empty": False, "drift_iou": 0.8},
            {"frame_idx": 20, "empty": False, "drift_iou": 0.7},
            {"frame_idx": 200, "empty": True, "drift_iou": 0.4},
            {"frame_idx": 210, "empty": True, "drift_iou": None},
            {"frame_idx": 220, "empty": False, "drift_iou": 0.2},
        ]

    def test_tach_dung_hai_ben(self):
        kq = tach_theo_khung(self._mau(), 0, 20)
        assert kq["khung"] == [[0, 20]]
        assert kq["trong_khung"] == {"n": 3, "n_empty": 0, "n_empty_do_duoc": 3, "empty_frac": 0.0,
                                     "n_drift": 3, "drift_iou_mean": 0.8,
                                     # 3 mẫu < MIN_SAMPLES ⇒ p05 chưa công bố (None ≠ 0)
                                     "drift_iou_p05": None, "drift_iou_p05_n": 3,
                                     "drift_iou_p05_nguong": MIN_SAMPLES}
        assert kq["ngoai_khung"] == {"n": 3, "n_empty": 2, "n_empty_do_duoc": 3, "empty_frac": 0.667,
                                     "n_drift": 2, "drift_iou_mean": 0.3,
                                     "drift_iou_p05": None, "drift_iou_p05_n": 2,
                                     "drift_iou_p05_nguong": MIN_SAMPLES}
        assert kq["khong_ro_khung"]["n"] == 0

    def test_bien_bao_gom_hai_dau(self):
        """`dau`/`cuoi` là BAO GỒM: frame 0 và frame 20 phải nằm trong khung."""
        assert tach_theo_khung(self._mau(), 0, 0)["trong_khung"]["n"] == 1
        assert tach_theo_khung(self._mau(), 20, 20)["trong_khung"]["n"] == 1

    def test_dao_nguoc_dau_cuoi_van_dung(self):
        """Người dùng gõ `105:0` ⇒ phải hiểu là 0..105, không trả về khung rỗng."""
        assert tach_theo_khung(self._mau(), 20, 0)["khung"] == [[0, 20]]

    def test_khung_rong_tra_none_khong_phai_0(self):
        """Không có mẫu nào trong khung ⇒ `None` (chưa đo), KHÔNG được là `0,0`/`0 %`."""
        kq = tach_theo_khung(self._mau(), 1000, 2000)
        assert kq["trong_khung"] == {"n": 0, "n_empty": 0, "n_empty_do_duoc": 0, "empty_frac": None,
                                     "n_drift": 0, "drift_iou_mean": None,
                                     "drift_iou_p05": None, "drift_iou_p05_n": 0,
                                     "drift_iou_p05_nguong": MIN_SAMPLES}

    def test_mau_khong_co_frame_idx_vao_khong_ro_khung(self):
        """`frame_idx` None (mẫu chờ bị cắt) không được rơi vào bên nào ⇒ không làm sai mẫu số."""
        mau = self._mau() + [{"frame_idx": None, "empty": True, "drift_iou": None}]
        kq = tach_theo_khung(mau, 0, 20)
        assert kq["trong_khung"]["n"] == 3
        assert kq["ngoai_khung"]["n"] == 3
        assert kq["khong_ro_khung"]["n"] == 1
        assert kq["khong_ro_khung"]["empty_frac"] == 1.0

    def test_empty_none_khong_vao_mau_so(self):
        """Mẫu chưa đo `empty` (None) không được tính là "không rỗng"."""
        assert thong_ke_mau([{"frame_idx": 1, "empty": None, "drift_iou": 0.5}]) == {
            "n": 1, "n_empty": 0, "n_empty_do_duoc": 0, "empty_frac": None, "n_drift": 1,
            "drift_iou_mean": 0.5, "drift_iou_p05": None, "drift_iou_p05_n": 1,
            "drift_iou_p05_nguong": MIN_SAMPLES}


class TestP05TheoKhung:
    """`p05` và điều kiện ticket 14 phải tính được **theo khung** (19-11).

    Lý do:

    1. Phụ lục báo cáo (PR #46) công bố "`p05` trong khung của `binh1` = 0,000 với n = 60" —
       nhưng TRƯỚC bản này **không công cụ nào** tính được: `low_p05_low_empty` chạy trên cả
       dãy, `thong_ke_mau` chỉ có `mean`. Số công bố mà không tái lập được bằng lệnh là đúng
       thứ repo này cấm.
    2. Điều kiện tiên quyết của ticket 14 ("`p05 < 0,30` **và** `empty_frac < 3 %`") chỉ
       ĐẠT khi lọc theo khung: cả phiên `binh1` có p05 0,663–0,720 (khoẻ) vì ngoài khung
       vật đã rời khung ⇒ `empty` cao; trong khung thì p05 = 0,000 với `empty` 1,6–1,8 %.
       Hàm phân biệt hai chuyện đó nên chúng KHÔNG còn là bản sao của nhau.
    """

    @staticmethod
    def _mau(n_trong=40, n_rong=0):
        """`n_trong` mẫu TRONG khung (drift xen kẽ 0,0 và 0,9 ⇒ p05 = 0), `n_rong` mẫu rỗng."""
        mau = []
        for i in range(n_trong):
            mau.append({"frame_idx": i, "empty": False,
                        "drift_iou": 0.0 if i % 10 == 0 else 0.9})
        for i in range(n_rong):
            mau.append({"frame_idx": 500 + i, "empty": True, "drift_iou": None})
        return mau

    def test_p05_tinh_tren_mau_trong_khung(self):
        kq = tach_theo_khung(self._mau(), 0, 39)
        assert kq["trong_khung"]["drift_iou_p05"] == 0.0
        assert kq["trong_khung"]["drift_iou_p05_n"] == 40
        # NGOÀI khung toàn mask rỗng ⇒ không có mẫu drift ⇒ p05 là None (CHƯA ĐO), không phải 0
        assert kq["ngoai_khung"]["drift_iou_p05"] is None

    def test_p05_dang_mau_30_nhu_moi_noi_khac(self):
        """Ngưỡng công bố p05 phải là MỘT con số (30) ở mọi nơi, kèm `_n` + `_nguong`."""
        kq = tach_theo_khung(self._mau(n_trong=MIN_SAMPLES - 1), 0, 100)
        assert kq["trong_khung"]["drift_iou_p05"] is None
        assert kq["trong_khung"]["drift_iou_p05_n"] == MIN_SAMPLES - 1
        assert kq["trong_khung"]["drift_iou_p05_nguong"] == MIN_SAMPLES
        kq2 = tach_theo_khung(self._mau(n_trong=MIN_SAMPLES), 0, 100)
        assert kq2["trong_khung"]["drift_iou_p05"] is not None

    def test_dieu_kien_ticket_14_theo_khung(self):
        """Trong khung: p05 = 0 **và** empty 0 % ⇒ cờ nói được điều `empty_frac` KHÔNG nói.

        Ca phản chứng: cùng `empty` 0 % nhưng p05 cao (0,9) ⇒ KHÔNG đạt điều kiện, tức hàm
        không chỉ là bản sao của `empty_frac`.
        """
        dat = tach_theo_khung(self._mau(n_trong=40), 0, 39)
        assert dat["trong_khung"]["empty_frac"] == 0.0
        assert dat["dieu_kien_ticket_14"]["trong_khung"]["dat"] is True
        khoe = [{"frame_idx": i, "empty": False, "drift_iou": 0.9} for i in range(40)]
        khong_dat = tach_theo_khung(khoe, 0, 39)
        assert khong_dat["trong_khung"]["empty_frac"] == 0.0
        assert khong_dat["dieu_kien_ticket_14"]["trong_khung"]["dat"] is False

    def test_dieu_kien_ticket_14_false_khi_empty_vuot_tran(self):
        """Nhánh quyết định của 5 lần chạy thật: `empty` 3,0–3,6 % ⇒ `False` (đo rồi, KHÔNG đạt).

        5 file `113932/115215/115231/141626/135451` có `p05 = 0,000` **và** `empty` 3,0–3,6 % —
        nếu hàm chỉ so p05 thì chúng bị gọi là ĐẠT sai.
        """
        # 40 mẫu, 2 rỗng (5 %) ⇒ p05 = 0 nhưng empty vượt trần 3 %
        mau = [{"frame_idx": i, "empty": False, "drift_iou": 0.0 if i % 8 == 0 else 0.9}
               for i in range(40)]
        mau[5]["empty"] = mau[15]["empty"] = True
        kq = tach_theo_khung(mau, 0, 39)
        dk = kq["dieu_kien_ticket_14"]["trong_khung"]
        assert kq["trong_khung"]["drift_iou_p05"] == 0.0
        assert dk["dat"] is False
        assert dk["ly_do"]                                  # phải nói VÌ SAO không đạt

    def test_dieu_kien_ticket_14_none_khi_qua_it_mau_khai_empty(self):
        """1 dòng khai `empty=0` + 59 dòng TRỐNG ⇒ `empty_frac = 0,0` nhưng đó là **chưa đo**.

        Cùng luật với `low_p05_low_empty` (`len(known) >= min_measured`); thiếu guard này thì cờ
        bật `ĐẠT` trên dữ liệu chưa khai cờ rỗng (review độc lập 19-11, P2).
        """
        mau = [{"frame_idx": i, "empty": None, "drift_iou": 0.0 if i % 8 == 0 else 0.9}
               for i in range(60)]
        mau[0]["empty"] = False                              # chỉ 1 mẫu khai
        kq = tach_theo_khung(mau, 0, 59)
        assert kq["trong_khung"]["empty_frac"] == 0.0        # số vẫn là 0,0 …
        dk = kq["dieu_kien_ticket_14"]["trong_khung"]
        assert dk["dat"] is None                              # … nhưng phán quyết là CHƯA ĐO
        assert "mẫu khai" in dk["ly_do"]

    def test_dieu_kien_ticket_14_none_khi_chua_do(self):
        """Không mẫu nào trong khung ⇒ `dat` là None (CHƯA ĐO), KHÔNG phải False."""
        kq = tach_theo_khung(self._mau(n_trong=5), 900, 999)
        assert kq["dieu_kien_ticket_14"]["trong_khung"]["dat"] is None
        assert kq["dieu_kien_ticket_14"]["trong_khung"]["ly_do"] != ""


class TestNhieuKhung:
    """`tach_theo_cac_khung` — nhiều khung vì `binh1` có **2 đoạn** vật còn trong khung.

    Số kỳ vọng tính tay trên 5 mẫu:
      frame 5 (khung 0:10), 20 (khung 15:30), 100 (ngoài) — empty 0,0,1 · drift 0,9,0,8,0,3
    """

    @staticmethod
    def _mau():
        return [
            {"frame_idx": 5, "empty": False, "drift_iou": 0.9},
            {"frame_idx": 20, "empty": False, "drift_iou": 0.8},
            {"frame_idx": 100, "empty": True, "drift_iou": 0.3},
        ]

    def test_gop_moi_khung_vao_trong_khung(self):
        kq = tach_theo_cac_khung(self._mau(), [(0, 10), (15, 30)])
        assert kq["khung"] == [[0, 10], [15, 30]]
        assert kq["trong_khung"]["n"] == 2
        assert kq["trong_khung"]["empty_frac"] == 0.0
        assert kq["trong_khung"]["drift_iou_mean"] == 0.85
        assert kq["ngoai_khung"]["n"] == 1
        assert kq["ngoai_khung"]["empty_frac"] == 1.0

    def test_mot_khung_van_chay_nhu_cu(self):
        kq = tach_theo_cac_khung(self._mau(), [(0, 10)])
        assert kq["trong_khung"]["n"] == 1
        assert kq["ngoai_khung"]["n"] == 2

    def test_khong_co_khung_nao_thi_bao_loi(self):
        """Danh sách rỗng ⇒ `ValueError` (KHÔNG lặng lẽ coi mọi mẫu là 'ngoài khung')."""
        with pytest.raises(ValueError):
            tach_theo_cac_khung(self._mau(), [])


def test_khung_chong_nhau_khong_dem_hai_lan():
    """Hai khung chồng nhau ⇒ mẫu nằm trong vùng chồng chỉ được đếm MỘT lần.

    Nếu cài bằng `sum(...)` cho từng khung thay vì `any(...)` thì `n` bị nhân đôi và tỉ lệ rỗng bị
    bóp méo (review vòng 2, P3).
    """
    rows = [{"frame_idx": 7, "empty": False, "drift_iou": 0.9}]
    kq = tach_theo_cac_khung(rows, [(0, 10), (5, 15)])
    assert kq["trong_khung"]["n"] == 1
    assert kq["ngoai_khung"]["n"] == 0


def test_khong_khai_khung_nao_la_loi_lap_trinh():
    """Danh sách khung RỖNG ⇒ `ValueError`, không được lặng lẽ coi "mọi mẫu là ngoài khung"."""
    with pytest.raises(ValueError):
        tach_theo_cac_khung([{"frame_idx": 1, "empty": False, "drift_iou": 0.5}], [])
