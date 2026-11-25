"""Test cho `scripts/replay_latch_settle.py` — đo chi phí ẩn overlay của cổng nghi (KHÔNG model).

Vì sao có: phiên `demoip_1124-125109` cho thấy latch không có đường xoá nào (re-ID tắt) ⇒ 44,3 %
phiên chỉ có ô nét đứt dù hệ đã bám lại đúng vật. Muốn nói "sửa xong rẻ/đắt bao nhiêu" thì phải
đếm được trên chính CSV đã ghi, không được ước lượng bằng lời.
"""
import csv
import json

import scripts.replay_latch_settle as rls
from src.identity_guard import (  # noqa: E402
    DEFAULT_LOST_RESET_STREAK,
    DEFAULT_REACQ_GRACE_STEPS,
)

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

    def test_mau_so_chi_gom_phien_DO_DUOC(self, tmp_path, monkeypatch, capsys):
        """REVIEW 24-11 (P1-b): CSV cũ thiếu cột `mask_area` thì cổng KHÔNG THỂ bật (ô dựng lại rỗng).

        Đếm chúng vào mẫu số làm loãng tỉ lệ (38,3 % frame trong bộ 39 phiên) — đúng bẫy
        "0/None ≠ đã đo". Test: 1 phiên đo được (31 frame, ẩn 31) + 1 phiên KHÔNG đo được
        (1000 frame) ⇒ `pct_frame_an` phải là 100 %, KHÔNG phải 3 %.
        """
        _ghi_csv(tmp_path / "demoip_moi_metrics.csv",
                 _phien([100] * 10 + [400] + [400] * 30))
        with open(tmp_path / "demoip_cu_metrics.csv", "w", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow(["frame_idx", "center_x", "center_y", "bbox_w", "bbox_h"])
            for i in range(1000):
                w.writerow([i, 10, 10, 0, 0])
        out = tmp_path / "kq.json"
        monkeypatch.setattr(rls, "REPO_ROOT", tmp_path)
        # tmp_path không phải repo git ⇒ phải giả `_git`, nếu không `git_loi` làm exit 1
        monkeypatch.setattr(rls, "_git", lambda *a: "abc1234" if a[:1] == ("rev-parse",) else "")
        assert rls.main(["--glob", "demoip_*_metrics.csv", "--settle", "0,8",
                         "--out", str(out)]) == 0
        t = json.loads(out.read_text(encoding="utf-8"))["tong"][f"0|{DEFAULT_LOST_RESET_STREAK}"]
        assert t["so_phien_do_duoc"] == 1 and t["so_frame_do_duoc"] == 41
        assert t["so_phien_bo_qua"] == 1 and t["so_frame_bo_qua"] == 1000
        assert t["pct_frame_an"] == round(100.0 * 31 / 41, 2), \
            "mẫu số phải chỉ gồm phiên ĐO ĐƯỢC (không trộn 1000 frame không đo được)"

    def test_khong_phien_nao_do_duoc_la_loi(self, tmp_path, monkeypatch, capsys):
        """0 phiên đo được KHÔNG phải "0 lần báo" — phải exit 1."""
        with open(tmp_path / "demoip_cu_metrics.csv", "w", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow(["frame_idx", "center_x", "center_y", "bbox_w", "bbox_h"])
            w.writerow([0, 10, 10, 0, 0])
        monkeypatch.setattr(rls, "REPO_ROOT", tmp_path)
        monkeypatch.setattr(rls, "_git", lambda *a: "abc1234" if a[:1] == ("rev-parse",) else "")
        assert rls.main(["--glob", "demoip_*_metrics.csv"]) == 1
        assert "KHÔNG phiên nào ĐO ĐƯỢC" in capsys.readouterr().err

    def test_git_hong_thi_exit_1_va_co_git_loi(self, tmp_path, monkeypatch, capsys):
        """REVIEW 24-11 (P2): git lỗi mà vẫn exit 0 ⇒ artifact trông "tái lập được" với rev None."""
        _ghi_csv(tmp_path / "demoip_x_metrics.csv",
                 _phien([100] * 10 + [400] + [400] * 30))
        out = tmp_path / "kq.json"
        monkeypatch.setattr(rls, "REPO_ROOT", tmp_path)
        monkeypatch.setattr(rls, "_git", lambda *a: None)
        assert rls.main(["--glob", "demoip_*_metrics.csv", "--out", str(out)]) == 1
        payload = json.loads(out.read_text(encoding="utf-8"))
        assert payload["git_rev"] is None and payload["git_loi"]
        assert "KHÔNG tái lập được" in capsys.readouterr().err

    def test_ghi_artifact_co_provenance(self, tmp_path, monkeypatch):
        _ghi_csv(tmp_path / "demoip_x_metrics.csv",
                 _phien([100] * 10 + [400] + [400] * 30))
        out = tmp_path / "kq.json"
        monkeypatch.setattr(rls, "REPO_ROOT", tmp_path)
        monkeypatch.setattr(rls, "_git", lambda *a: "abc1234" if a[:1] == ("rev-parse",) else "")
        assert rls.main(["--glob", "demoip_*_metrics.csv", "--settle", "0,8",
                         "--out", str(out)]) == 0
        payload = json.loads(out.read_text(encoding="utf-8"))
        assert payload["settle_list"] == [0, 8]
        khoa = f"0|{DEFAULT_LOST_RESET_STREAK}"
        assert payload["lost_reset_list"] == [DEFAULT_LOST_RESET_STREAK]
        assert payload["reacq_grace_steps"] == DEFAULT_REACQ_GRACE_STEPS
        assert payload["tong"][khoa]["frame_an"] == 31
        assert payload["git_rev"] == "abc1234" and payload["git_loi"] is None
        assert payload["tong"][f"8|{DEFAULT_LOST_RESET_STREAK}"]["frame_chua_xac_minh"] > 0
        for k in ("git_rev", "git_dirty", "git_dirty_code", "lenh", "do_luc", "nguon", "frame_shape",
                  "lost_reset_list", "lost_reset_mac_dinh", "reacq_grace_steps"):
            assert k in payload, f"thiếu provenance `{k}` (AGENTS §6)"

    def test_settle_am_bi_tu_choi(self, monkeypatch):
        monkeypatch.setattr(rls, "REPO_ROOT", __import__("pathlib").Path("/tmp"))
        assert rls.main(["--settle", "0,-3"]) == 2
