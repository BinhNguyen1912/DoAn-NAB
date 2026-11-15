"""`scripts/gt_check_silhouette.py` — bắt 2 lỗi GT đã xảy ra thật ngày 15-11.

Vì sao có bộ kiểm này: `score_miou --check-index` chỉ hỏi "file có giải mã được" nên một bộ GT vẽ bằng
**công cụ hình chữ nhật chỉ ra viền** (lấp đầy 15–20 % khung bao) hoặc **copy-paste giữa các frame**
vẫn được báo "hợp lệ" và chấm ra 0,03 — trông như "model bám kém".

Ghim ở đây: viền rỗng ⇒ cảnh báo; hình chữ nhật đặc ⇒ cảnh báo (phải khai `hop_bao`); vật thuôn thật
⇒ KHÔNG cảnh báo; copy-paste ⇒ cảnh báo; thiếu file / sai cỡ ⇒ lỗi CHẶN (mã 2).
"""

import json
from pathlib import Path

import numpy as np
import pytest

from scripts import gt_check_silhouette as gc

H, W = 200, 120


def _vien_rong(h=120, w=60, net=8):
    """Khung chữ nhật CHỈ CÓ VIỀN — đúng thứ người dùng vẽ ngày 15-11."""
    m = np.zeros((H, W), bool)
    m[40:40 + h, 30:30 + w] = True
    m[40 + net:40 + h - net, 30 + net:30 + w - net] = False
    return m


def _hinh_chu_nhat(h=120, w=60):
    m = np.zeros((H, W), bool)
    m[40:40 + h, 30:30 + w] = True
    return m


def _vat_thuon(h=120, w=60):
    """Vật thuôn như chai xịt: thân rộng + cổ hẹp ⇒ lấp đầy khung bao ~0,6."""
    m = np.zeros((H, W), bool)
    m[100:160, 30:90] = True
    m[40:100, 52:68] = True
    return m


def _bo_gt(tmp_path: Path, masks: dict) -> Path:
    """Dựng một bộ GT trên đĩa: `masks = {frame_idx: mask}` + `index.json`."""
    import cv2

    (tmp_path / "index.json").write_text(json.dumps({
        "clip": "data/binh1.mp4", "nguoi_gan": "Bình", "dang_gt": "silhouette",
        "frame_hw": [H, W], "frames": [{"frame_idx": i} for i in sorted(masks)],
    }), encoding="utf-8")
    for i, m in masks.items():
        cv2.imwrite(str(tmp_path / f"gt_{i:06d}.png"), (np.asarray(m) * 255).astype(np.uint8))
    return tmp_path


class TestHinhDang:
    def test_vien_rong_bi_canh_bao(self):
        kq = gc.kiem_mot_frame(_vien_rong())
        assert kq["lap_day"] < gc.FILL_MIN
        assert any("VIỀN RỖNG" in x for x in kq["canh_bao"])

    def test_hinh_chu_nhat_dac_bi_canh_bao(self):
        kq = gc.kiem_mot_frame(_hinh_chu_nhat())
        assert kq["lap_day"] > gc.FILL_MAX
        assert any("HÌNH CHỮ NHẬT" in x for x in kq["canh_bao"])

    def test_vat_thuon_khong_bi_canh_bao(self):
        kq = gc.kiem_mot_frame(_vat_thuon())
        assert gc.FILL_MIN <= kq["lap_day"] <= gc.FILL_MAX
        assert kq["canh_bao"] == []

    def test_to_ca_nen_bi_canh_bao(self):
        kq = gc.kiem_mot_frame(np.ones((H, W), bool))
        assert any("tô cả nền" in x for x in kq["canh_bao"])

    def test_gt_rong_khong_canh_bao_chi_danh_dau(self):
        """GT rỗng là hợp lệ (vật đã rời khung) — nhưng phải nói ra là frame đó KHÔNG được chấm."""
        kq = gc.kiem_mot_frame(np.zeros((H, W), bool))
        assert kq["gt_rong"] is True and kq["canh_bao"] == []


class TestBoGt:
    def test_copy_paste_bi_canh_bao(self, tmp_path):
        m = _vat_thuon()
        dong, loi = gc.kiem_bo(_bo_gt(tmp_path, {0: m, 1: m.copy()}))
        assert not loi
        assert all(any("trùng khít" in x for x in d["canh_bao"]) for d in dong)

    def test_hai_frame_khac_nhau_thi_khong_bao_trung(self, tmp_path):
        a = _vat_thuon()
        b = np.roll(a, 25, axis=1)
        dong, loi = gc.kiem_bo(_bo_gt(tmp_path, {0: a, 1: b}))
        assert not loi and not any(d["canh_bao"] for d in dong)

    def test_thieu_file_la_loi_chan(self, tmp_path):
        _bo_gt(tmp_path, {0: _vat_thuon()})
        (tmp_path / "index.json").write_text(json.dumps({
            "frame_hw": [H, W], "frames": [{"frame_idx": 0}, {"frame_idx": 5}]}),
            encoding="utf-8")
        dong, loi = gc.kiem_bo(tmp_path)
        assert any("thiếu" in x for x in loi)
        assert any("THIẾU FILE GT" in (d.get("canh_bao") or [""])[0] for d in dong)

    def test_sai_kich_thuoc_la_loi_chan(self, tmp_path):
        import cv2

        _bo_gt(tmp_path, {0: _vat_thuon()})
        cv2.imwrite(str(tmp_path / "gt_000000.png"), np.full((10, 10), 255, np.uint8))
        _dong, loi = gc.kiem_bo(tmp_path)
        assert any("sai kích thước" in x for x in loi)

    def test_main_ma_1_khi_co_canh_bao_va_2_khi_loi_chan(self, tmp_path, capsys):
        _bo_gt(tmp_path, {0: _vien_rong()})
        assert gc.main(["--gt", str(tmp_path)]) == 1
        assert "VIỀN RỖNG" in capsys.readouterr().out

        _bo_gt(tmp_path, {0: _vat_thuon()})
        (tmp_path / "gt_000000.png").unlink()
        assert gc.main(["--gt", str(tmp_path)]) == 2


class TestAnhCoAlpha:
    """PNG 4 kênh (RGBA) là chuyện THƯỜNG (canvas/Chrome, Paint.NET) — alpha 255 khắp nơi không được
    biến GT thành "phủ kín khung" (đã xảy ra 15-11: mIoU sụp còn ~0,1 mà không báo gì)."""

    def test_alpha_255_khong_lam_gt_thanh_toan_khung(self, tmp_path):
        import cv2

        rgba = np.zeros((H, W, 4), np.uint8)
        rgba[60:140, 40:80, :3] = 255          # chỉ vùng vật là trắng
        rgba[:, :, 3] = 255                     # alpha ĐỤC khắp nơi
        cv2.imwrite(str(tmp_path / "gt_000000.png"), rgba)
        mask = gc.doc_mask(tmp_path / "gt_000000.png")
        assert mask.shape == (H, W)
        assert int(mask.sum()) == 80 * 40, "phải chỉ đếm vùng trắng, không đếm alpha"

    def test_doc_mask_binary_3_kenh(self, tmp_path):
        import cv2

        m = _vat_thuon()
        cv2.imwrite(str(tmp_path / "gt_000000.png"), (m * 255).astype(np.uint8))
        assert gc.doc_mask(tmp_path / "gt_000000.png").shape == (H, W)


class TestIoU:
    def test_trung_khit_bang_1_va_roi_nhau_bang_0(self):
        a = _vat_thuon()
        assert gc.iou(a, a) == pytest.approx(1.0)
        assert gc.iou(a, np.zeros_like(a)) == 0.0

    def test_roi_rong_khong_phai_1(self):
        z = np.zeros((H, W), bool)
        assert gc.iou(z, z) == 0.0
