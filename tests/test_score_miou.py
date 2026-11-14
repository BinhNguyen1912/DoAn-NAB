"""`scripts/score_miou.py` — thước đo "BÁM ĐÚNG" (mIoU vs GT). Việc #6 của plan.

Đây là thước đo duy nhất trong repo nói được đúng/sai (`drift_iou`/`stability` chỉ là độ tự nhất
quán). Vì vậy phần THUẦN của nó (IoU, quy tắc chấm, kiểm `index.json`) phải được ghim bằng test —
một lỗi ở đây làm sai toàn bộ phần "đánh giá chất lượng phân đoạn" trong báo cáo.

Bốn bẫy được ghim:
1. `IoU(rỗng, rỗng) = 1,0` — GT rỗng KHÔNG phải "bám đúng tuyệt đối" ⇒ không chấm (None).
2. Model rỗng mà GT có vật ⇒ **0,0** (không được gộp vào "không đo được").
3. Thiếu file mask của model ⇒ **chưa chạy**, không phải bám sai ⇒ `None` + đếm riêng.
4. `mIoU = None` khi không chấm được frame nào — không bao giờ in 0 cho "chưa đo".
"""

import json

import numpy as np
import pytest

from scripts import score_miou as sm


def _mask(arr):
    return np.asarray(arr, dtype=np.uint8)


class TestIoU:
    def test_trung_khit_bang_1(self):
        a = np.zeros((10, 10), np.uint8)
        a[2:6, 2:6] = 255
        assert sm.iou(a, a) == pytest.approx(1.0)

    def test_roi_rac_bang_0_khi_gt_co_vat_va_pred_rong(self):
        gt = _mask(np.zeros((10, 10)))
        gt[2:6, 2:6] = 255
        pred = _mask(np.zeros((10, 10)))
        assert sm.iou(pred, gt) == 0.0          # KHÔNG phải None

    def test_gt_rong_thi_khong_cham(self):
        """`IoU(rỗng, rỗng)` theo công thức là 1,0 — nhận nó là "bám đúng tuyệt đối" thì vô nghĩa."""
        rong = _mask(np.zeros((10, 10)))
        assert sm.iou(rong, rong) is None
        pred = _mask(np.zeros((10, 10)))
        pred[0:2, 0:2] = 255
        assert sm.iou(pred, rong) is None

    def test_mot_nua_dien_tich_cho_iou_1_3(self):
        gt = _mask(np.zeros((4, 4)))
        gt[0:2, :] = 255     # 8 pixel
        pred = _mask(np.zeros((4, 4)))
        pred[1:3, :] = 255  # 8 pixel, giao 4
        # giao 4, hợp 12 ⇒ 1/3
        assert sm.iou(pred, gt) == pytest.approx(1 / 3, abs=1e-6)

    def test_lech_kich_thuoc_bao_loi(self):
        with pytest.raises(ValueError, match="lệch kích thước"):
            sm.iou(np.zeros((4, 4)), np.zeros((5, 5)))

    def test_mask_3_kenh_van_doc_duoc(self, tmp_path):
        import cv2

        img = np.zeros((4, 4, 3), np.uint8)
        img[:, :, 2] = 255                                # chỉ kênh đỏ
        path = tmp_path / "m.png"
        cv2.imwrite(str(path), img)
        assert sm.doc_mask(path).all()


class TestCham:
    def _gt(self, tmp_path, idx, arr):
        import cv2

        (tmp_path / f"gt_{idx:06d}.png").write_bytes(b"")
        cv2.imwrite(str(tmp_path / f"gt_{idx:06d}.png"), _mask(arr) * 255)

    def _pred(self, tmp_path, idx, arr):
        import cv2

        path = tmp_path / f"mask_{idx:06d}.png"
        cv2.imwrite(str(path), _mask(arr) * 255)
        return path

    def test_miou_trung_binh_tren_cac_frame_cham_duoc(self, tmp_path):
        gt_dir, pred_dir = tmp_path / "gt", tmp_path / "pred"
        gt_dir.mkdir()
        pred_dir.mkdir()
        hoan_hao = np.zeros((6, 6))
        hoan_hao[1:3, 1:3] = 1
        self._gt(gt_dir, 0, hoan_hao)
        self._pred(pred_dir, 0, hoan_hao)
        self._gt(gt_dir, 5, hoan_hao)
        self._pred(pred_dir, 5, np.zeros((6, 6)))          # model rỗng ⇒ 0,0
        frames = [{"frame_idx": 0, "pred_path": str(pred_dir / "mask_000000.png")},
                  {"frame_idx": 5, "pred_path": str(pred_dir / "mask_000005.png")}]
        kq = sm.cham(frames, gt_dir)
        assert kq["n_cham"] == 2
        assert kq["mIoU"] == pytest.approx(0.5)
        assert kq["mIoU_p05"] is None                      # < 5 mẫu ⇒ không bịa p05

    def test_thieu_mask_cua_model_khong_bi_coi_la_0(self, tmp_path):
        gt_dir = tmp_path / "gt"
        gt_dir.mkdir()
        self._gt(gt_dir, 0, np.ones((4, 4)))
        kq = sm.cham([{"frame_idx": 0, "pred_path": str(tmp_path / "khong_co.png")}], gt_dir)
        assert kq["n_cham"] == 0 and kq["mIoU"] is None
        assert kq["so_frame_thieu_mask"] == 1
        assert kq["frames"][0]["ly_do"] == "thiếu mask của model"

    def test_gt_rong_dem_rieng_khong_vao_miou(self, tmp_path):
        gt_dir, pred_dir = tmp_path / "gt", tmp_path / "pred"
        gt_dir.mkdir()
        pred_dir.mkdir()
        self._gt(gt_dir, 0, np.zeros((4, 4)))
        self._pred(pred_dir, 0, np.ones((4, 4)))
        kq = sm.cham([{"frame_idx": 0, "pred_path": str(pred_dir / "mask_000000.png")}], gt_dir)
        assert kq["so_frame_gt_rong"] == 1 and kq["n_cham"] == 0 and kq["mIoU"] is None


class TestKiemIndex:
    def _index(self, tmp_path, **kw):
        base = {"clip": "data/binh1.mp4", "nguoi_gan": "Bình",
                "gt_do_model_goi_y": False, "frames": [{"frame_idx": 0}]}
        base.update(kw)
        return base

    def test_hop_le(self, tmp_path):
        (tmp_path / "gt_000000.png").write_bytes(b"x")
        assert sm.kiem_index(self._index(tmp_path), tmp_path) == []

    def test_thieu_file_gt_bao_loi(self, tmp_path):
        loi = sm.kiem_index(self._index(tmp_path), tmp_path)
        assert any("thiếu file GT" in x for x in loi)

    def test_thieu_nguoi_gan_bao_loi(self, tmp_path):
        (tmp_path / "gt_000000.png").write_bytes(b"x")
        loi = sm.kiem_index(self._index(tmp_path, nguoi_gan=""), tmp_path)
        assert any("nguoi_gan" in x for x in loi)

    def test_gt_do_model_goi_y_bi_tu_choi(self, tmp_path):
        """Chấm mIoU trên mask do CHÍNH model sinh ra = đo chính nó, không phải đo chất lượng."""
        (tmp_path / "gt_000000.png").write_bytes(b"x")
        loi = sm.kiem_index(self._index(tmp_path, gt_do_model_goi_y=True), tmp_path)
        assert any("gợi ý" in x for x in loi)

    def test_frame_trung_va_am(self, tmp_path):
        (tmp_path / "gt_000000.png").write_bytes(b"x")
        loi = sm.kiem_index(self._index(tmp_path, frames=[{"frame_idx": 0}, {"frame_idx": 0},
                                                          {"frame_idx": -3}]), tmp_path)
        assert any("trùng" in x for x in loi) and any("không hợp lệ" in x for x in loi)

    def test_frames_rong(self, tmp_path):
        assert any("rỗng" in x for x in sm.kiem_index(self._index(tmp_path, frames=[]), tmp_path))


class TestCli:
    def test_score_khong_co_index_thi_bao_loi(self, tmp_path, capsys):
        assert sm.main(["score", "--gt", str(tmp_path), "--pred-dir", str(tmp_path)]) == 2
        assert "không thấy" in capsys.readouterr().out

    def test_check_index_tra_ma_1_khi_gt_hong(self, tmp_path, capsys):
        (tmp_path / "index.json").write_text(json.dumps({"clip": "x", "frames": []}),
                                             encoding="utf-8")
        assert sm.main(["score", "--gt", str(tmp_path), "--pred-dir", str(tmp_path),
                        "--check-index"]) == 1

    def test_score_ghi_artifact_va_miou_None_khi_khong_cham_duoc(self, tmp_path, monkeypatch):
        import cv2

        gt = tmp_path / "gt"
        gt.mkdir()
        (gt / "index.json").write_text(json.dumps({
            "clip": "data/binh1.mp4", "nguoi_gan": "Bình", "frames": [{"frame_idx": 0}]}),
            encoding="utf-8")
        cv2.imwrite(str(gt / "gt_000000.png"), np.full((4, 4), 255, np.uint8))
        out = tmp_path / "art.json"
        import scripts.measure_watchdog as mw

        monkeypatch.setattr(mw, "_git_provenance", lambda: ("abc1234", False, False, None))
        # pred-dir rỗng ⇒ thiếu mask ⇒ mIoU None, mã thoát 1 (không phải 0 = "đạt")
        ma = sm.main(["score", "--gt", str(gt), "--pred-dir", str(tmp_path / "pred"),
                      "--out", str(out)])
        assert ma == 1
        payload = json.loads(out.read_text(encoding="utf-8"))
        assert payload["ket_qua"]["mIoU"] is None
        assert payload["meta"]["git_rev"] == "abc1234"
        assert "GT rỗng không chấm" in payload["meta"]["dinh_nghia"]


class TestMaskHongKhongLamChetCaLanCham:
    """Mask 1×1 (model không trả mask) từng làm `iou()` ném ValueError ⇒ chết cả lần chấm."""

    def test_lech_kich_thuoc_duoc_dem_rieng(self, tmp_path):
        import cv2

        gt_dir, pred_dir = tmp_path / "gt", tmp_path / "pred"
        gt_dir.mkdir()
        pred_dir.mkdir()
        cv2.imwrite(str(gt_dir / "gt_000000.png"), np.full((6, 6), 255, np.uint8))
        cv2.imwrite(str(pred_dir / "mask_000000.png"), np.full((1, 1), 255, np.uint8))
        cv2.imwrite(str(gt_dir / "gt_000002.png"), np.full((6, 6), 255, np.uint8))
        cv2.imwrite(str(pred_dir / "mask_000002.png"), np.full((6, 6), 255, np.uint8))

        kq = sm.cham([{"frame_idx": 0, "pred_path": str(pred_dir / "mask_000000.png")},
                      {"frame_idx": 2, "pred_path": str(pred_dir / "mask_000002.png")}], gt_dir)
        assert kq["so_frame_mask_hong"] == 1
        assert kq["n_cham"] == 1 and kq["mIoU"] == pytest.approx(1.0)
        assert "mask hỏng" in kq["frames"][0]["ly_do"]

    def test_png_hong_khong_lam_chet(self, tmp_path):
        gt_dir, pred_dir = tmp_path / "gt", tmp_path / "pred"
        gt_dir.mkdir()
        pred_dir.mkdir()
        (gt_dir / "gt_000000.png").write_bytes("không phải ảnh".encode())
        (pred_dir / "mask_000000.png").write_bytes("không phải ảnh".encode())
        kq = sm.cham([{"frame_idx": 0, "pred_path": str(pred_dir / "mask_000000.png")}], gt_dir)
        assert kq["so_frame_mask_hong"] == 1 and kq["mIoU"] is None
