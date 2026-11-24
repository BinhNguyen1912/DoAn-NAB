"""Test cho `scripts/replay_latch_settle.py` — đo chi phí ẩn overlay của cổng nghi (KHÔNG model).

Vì sao có: phiên `demoip_1124-125109` cho thấy latch không có đường xoá nào (re-ID tắt) ⇒ 44,3 %
phiên chỉ có ô nét đứt dù hệ đã bám lại đúng vật. Muốn nói "sửa xong rẻ/đắt bao nhiêu" thì phải
đếm được trên chính CSV đã ghi, không được ước lượng bằng lời.
"""
import csv
import json

import scripts.replay_latch_settle as rls

HEADER = ["frame_idx", "center_x", "center_y", "bbox_w", "bbox_h", "mask_area"]


def _ghi_csv(path, rows):
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(HEADER)
        for r in rows:
            w.writerow(r)


def _phien(cx_list, w=100, h=100, area=5000, lost_at=()):
    """Chuỗi frame: tâm chạy theo `cx_list`; frame trong `lost_at` mất dấu (bbox 0)."""
    out = []
    for i, cx in enumerate(cx_list):
        if i in lost_at:
            out.append([i, "", "", 0, 0, 0])
        else:
            out.append([i, cx, 240, w, h, area])
    return out


class TestDocCot:
    def test_dung_lai_o_tu_tam_va_kich_thuoc(self, tmp_path):
        p = tmp_path / "a_metrics.csv"
        _ghi_csv(p, [[0, 100, 240, 60, 80, 1000]])
        rows = rls.doc_cot(p)
        assert rows[0]["bbox"] == (70, 200, 130, 280)
        assert rows[0]["co_mask"] is True

    def test_mat_dau_la_o_rong(self, tmp_path):
        p = tmp_path / "a_metrics.csv"
        _ghi_csv(p, [[0, "", "", 0, 0, 0]])
        rows = rls.doc_cot(p)
        assert rows[0]["bbox"] == (0, 0, 0, 0)
        assert rows[0]["co_mask"] is False

    def test_thieu_cot_mask_area_khac_mat_dau(self, tmp_path):
        """CSV 11 cột cũ: KHÔNG có `mask_area` ⇒ `co_mask_area` phải là False (không phải 'mất dấu')."""
        p = tmp_path / "a_metrics.csv"
        with open(p, "w", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow(["frame_idx", "center_x", "center_y", "bbox_w", "bbox_h"])
            w.writerow([0, 100, 240, 60, 80])
        rows = rls.doc_cot(p)
        assert rows[0]["co_mask_area"] is False
        assert rows[0]["co_mask"] is False


class TestReplay:
    def test_settle_0_an_toi_het_phien(self, tmp_path):
        """Tái lập hành vi CŨ: một cú nhảy ⇒ ẩn từ đó tới cuối, không có frame 'chưa xác minh'."""
        p = tmp_path / "a_metrics.csv"
        # 10 frame yên, frame 10 nhảy 300 px, rồi 30 frame yên
        _ghi_csv(p, _phien([100] * 10 + [400] + [400] * 30))
        rows = rls.doc_cot(p)
        out = rls.replay(rows, 0, (480, 640))
        assert out["fire"] == 1
        assert out["frame_an"] == 31               # 30 frame sau cú nhảy + chính frame nhảy
        assert out["frame_chua_xac_minh"] == 0

    def test_settle_8_ha_muc_nhung_khong_het_an(self, tmp_path):
        p = tmp_path / "a_metrics.csv"
        _ghi_csv(p, _phien([100] * 10 + [400] + [400] * 30))
        rows = rls.doc_cot(p)
        out = rls.replay(rows, 8, (480, 640))
        assert out["frame_chua_xac_minh"] > 0, "phải hạ mức sau 8 bước ổn định"
        assert out["frame_an"] > 0, "8 bước đầu vẫn phải ẨN (không hạ ngay)"
        assert out["frame_an"] + out["frame_chua_xac_minh"] == 31

    def test_mat_dau_khong_tinh_la_on_dinh(self, tmp_path):
        """Mask rỗng ⇒ không có gì để tin ⇒ KHÔNG hạ mức (đừng vẽ một vùng không tồn tại)."""
        p = tmp_path / "a_metrics.csv"
        _ghi_csv(p, _phien([100] * 10 + [400] + [400] * 30, lost_at=set(range(11, 41))))
        rows = rls.doc_cot(p)
        out = rls.replay(rows, 8, (480, 640))
        assert out["frame_an"] == 31
        assert out["frame_chua_xac_minh"] == 0

    def test_hai_luat_chay_tren_cung_du_lieu(self, tmp_path):
        p = tmp_path / "a_metrics.csv"
        _ghi_csv(p, _phien([100] * 10 + [400] + [400] * 30))
        rows = rls.doc_cot(p)
        cu = rls.replay(rows, 0, (480, 640))
        moi = rls.replay(rows, 8, (480, 640))
        assert cu["frame_an"] > moi["frame_an"], "settle phải GIẢM số frame mất hình"


class TestMain:
    def test_khong_co_csv_la_loi(self, tmp_path, monkeypatch, capsys):
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(rls, "REPO_ROOT", tmp_path)
        assert rls.main(["--glob", "khong_co_*.csv"]) == 1
        assert "KHÔNG đo được" in capsys.readouterr().err

    def test_ghi_artifact_co_provenance(self, tmp_path, monkeypatch):
        _ghi_csv(tmp_path / "demoip_x_metrics.csv",
                 _phien([100] * 10 + [400] + [400] * 30))
        out = tmp_path / "kq.json"
        monkeypatch.setattr(rls, "REPO_ROOT", tmp_path)
        assert rls.main(["--glob", "demoip_*_metrics.csv", "--settle", "0,8",
                         "--out", str(out)]) == 0
        payload = json.loads(out.read_text(encoding="utf-8"))
        assert payload["settle_list"] == [0, 8]
        assert payload["tong"]["0"]["frame_an"] == 31
        assert payload["tong"]["8"]["frame_chua_xac_minh"] > 0
        for k in ("git_rev", "git_dirty_code", "lenh", "do_luc", "nguon", "frame_shape"):
            assert k in payload, f"thiếu provenance `{k}` (AGENTS §6)"

    def test_settle_am_bi_tu_choi(self, monkeypatch):
        monkeypatch.setattr(rls, "REPO_ROOT", __import__("pathlib").Path("/tmp"))
        assert rls.main(["--settle", "0,-3"]) == 2
