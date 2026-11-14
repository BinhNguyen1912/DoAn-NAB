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
    read_samples,
    rolling_p05,
    static_control,
    summarize,
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
        assert kq["khung"] == [0, 20]
        assert kq["trong_khung"] == {"n": 3, "n_empty_do_duoc": 3, "empty_frac": 0.0,
                                     "n_drift": 3, "drift_iou_mean": 0.8}
        assert kq["ngoai_khung"] == {"n": 3, "n_empty_do_duoc": 3, "empty_frac": 0.667,
                                     "n_drift": 2, "drift_iou_mean": 0.3}
        assert kq["khong_ro_khung"]["n"] == 0

    def test_bien_bao_gom_hai_dau(self):
        """`dau`/`cuoi` là BAO GỒM: frame 0 và frame 20 phải nằm trong khung."""
        assert tach_theo_khung(self._mau(), 0, 0)["trong_khung"]["n"] == 1
        assert tach_theo_khung(self._mau(), 20, 20)["trong_khung"]["n"] == 1

    def test_dao_nguoc_dau_cuoi_van_dung(self):
        """Người dùng gõ `105:0` ⇒ phải hiểu là 0..105, không trả về khung rỗng."""
        assert tach_theo_khung(self._mau(), 20, 0)["khung"] == [0, 20]

    def test_khung_rong_tra_none_khong_phai_0(self):
        """Không có mẫu nào trong khung ⇒ `None` (chưa đo), KHÔNG được là `0,0`/`0 %`."""
        kq = tach_theo_khung(self._mau(), 1000, 2000)
        assert kq["trong_khung"] == {"n": 0, "n_empty_do_duoc": 0, "empty_frac": None,
                                     "n_drift": 0, "drift_iou_mean": None}

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
            "n": 1, "n_empty_do_duoc": 0, "empty_frac": None, "n_drift": 1,
            "drift_iou_mean": 0.5}
