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
        assert kq["mIoU_p05"] is None                      # < 30 mẫu ⇒ không bịa p05 (ticket #23)
        assert kq["mIoU_p05_n"] == 2                       # cỡ mẫu LUÔN có mặt cạnh con số

    def test_p05_chi_cong_bo_tu_nguong_dung_chung_30(self, tmp_path):
        """Ticket #23: trước đây ngưỡng riêng là **5** ⇒ `mIoU_p05` công bố từ 5 frame (≈ min).

        Đây là test bắt hồi quy của bẫy "p05 ở cỡ mẫu nhỏ chính là giá trị xấu nhất": 5 frame phải
        là `None`, 30 frame mới được công bố, và ngưỡng phải là **cùng hằng** với `status.json`.
        """
        from src import drift_samples as ds

        assert sm.MIN_SAMPLES == ds.MIN_SAMPLES
        gt_dir, pred_dir = tmp_path / "gt", tmp_path / "pred"
        gt_dir.mkdir()
        pred_dir.mkdir()
        hinh = np.zeros((6, 6))
        hinh[1:3, 1:3] = 1

        def cham_n(n):
            frames = []
            for idx in range(n):
                self._gt(gt_dir, idx, hinh)
                frames.append({"frame_idx": idx, "pred_path": self._pred(pred_dir, idx, hinh)})
            return sm.cham(frames, gt_dir)

        nam = cham_n(5)
        assert nam["n_cham"] == 5
        assert nam["mIoU_p05"] is None and nam["mIoU_p05_n"] == 5
        assert nam["mIoU"] == pytest.approx(1.0)     # trung bình VẪN công bố ở n nhỏ

        # 25 frame: đủ cho ngưỡng cũ 20 (và đương nhiên cho 5) ⇒ đây là ca bắt hồi quy thực sự.
        hai_muoi_lam = cham_n(25)
        assert hai_muoi_lam["mIoU_p05_n"] == 25 and hai_muoi_lam["mIoU_p05"] is None

        ba_muoi = cham_n(30)
        assert ba_muoi["mIoU_p05_n"] == 30
        assert ba_muoi["mIoU_p05"] == pytest.approx(1.0)

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

    # ── `mask_ngoai_gt`: đo phần mask TRÀN RA NGOÀI GT (15-11) ────────────────────────────────
    def test_mask_nam_hoan_toan_trong_gt_thi_tran_bang_0(self, tmp_path):
        """Mask nằm gọn trong GT (GT hộp bao) ⇒ `mIoU` bị chặn dưới 1, nhưng `tran` = 0."""
        gt_dir, pred_dir = tmp_path / "gt", tmp_path / "pred"
        gt_dir.mkdir()
        pred_dir.mkdir()
        box = np.zeros((10, 10))
        box[1:9, 1:9] = 1
        self._gt(gt_dir, 0, box)
        self._pred(pred_dir, 0, box)
        kq = sm.cham([{"frame_idx": 0, "pred_path": str(pred_dir / "mask_000000.png")}], gt_dir)
        assert kq["frames"][0]["mask_ngoai_gt"] == 0.0
        assert kq["mask_ngoai_gt_mean"] == 0.0

    def test_mask_tran_mot_nua_thi_tran_bang_0_5(self, tmp_path):
        gt_dir, pred_dir = tmp_path / "gt", tmp_path / "pred"
        gt_dir.mkdir()
        pred_dir.mkdir()
        gt = np.zeros((4, 4))
        gt[:, :2] = 1                      # nửa trái
        pred = np.zeros((4, 4))
        pred[:, 1:3] = 1                   # 8 px, chỉ 4 px nằm trong GT
        self._gt(gt_dir, 0, gt)
        self._pred(pred_dir, 0, pred)
        kq = sm.cham([{"frame_idx": 0, "pred_path": str(pred_dir / "mask_000000.png")}], gt_dir)
        assert kq["frames"][0]["mask_ngoai_gt"] == pytest.approx(0.5)
        assert kq["mask_ngoai_gt_max_frame"] == 0

    def test_mau_so_tran_loai_frame_mask_rong_va_co_dem_rieng(self, tmp_path):
        """Frame model trả mask RỖNG vẫn vào `mIoU` (0,0) nhưng KHÔNG vào trung bình "tràn" ⇒ phải có
        `mask_ngoai_gt_n` để con số không lạc quan một cách im lặng (P2 review 15-11)."""
        gt_dir, pred_dir = tmp_path / "gt", tmp_path / "pred"
        gt_dir.mkdir()
        pred_dir.mkdir()
        self._gt(gt_dir, 0, np.ones((4, 4)))
        self._pred(pred_dir, 0, np.ones((4, 4)))
        self._gt(gt_dir, 1, np.ones((4, 4)))
        self._pred(pred_dir, 1, np.zeros((4, 4)))          # model rỗng ⇒ IoU 0,0, không có "tràn"
        kq = sm.cham([{"frame_idx": 0, "pred_path": str(pred_dir / "mask_000000.png")},
                      {"frame_idx": 1, "pred_path": str(pred_dir / "mask_000001.png")}], gt_dir)
        assert kq["n_cham"] == 2
        assert kq["mask_ngoai_gt_n"] == 1 and kq["mask_ngoai_gt_mean"] == 0.0

    def test_model_rong_thi_tran_la_None_khong_phai_0(self, tmp_path):
        """Model rỗng ⇒ không có gì để 'tràn' ⇒ `None` (chưa đo), không phải 0,0 "hoàn hảo"."""
        gt_dir, pred_dir = tmp_path / "gt", tmp_path / "pred"
        gt_dir.mkdir()
        pred_dir.mkdir()
        self._gt(gt_dir, 0, np.ones((4, 4)))
        self._pred(pred_dir, 0, np.zeros((4, 4)))
        kq = sm.cham([{"frame_idx": 0, "pred_path": str(pred_dir / "mask_000000.png")}], gt_dir)
        assert kq["frames"][0]["mask_ngoai_gt"] is None
        assert kq["mask_ngoai_gt_mean"] is None

    def test_hoa_tran_chon_frame_nho_nhat_du_index_xep_nguoc(self, tmp_path):
        """HOÀ "tràn" lớn nhất: `max()` trơn lấy phần tử ĐẦU theo thứ tự `rows` ⇒ cùng một bộ GT mà
        index xếp ngược sẽ ra frame khác nhau. Quy ước (ghim ở đây): lấy **frame_idx nhỏ nhất**."""
        gt_dir, pred_dir = tmp_path / "gt", tmp_path / "pred"
        gt_dir.mkdir()
        pred_dir.mkdir()
        gt = np.zeros((6, 6))
        gt[1:5, 1:5] = 1                       # 16 px
        phu_kin = np.ones((6, 6))              # 36 px ⇒ tràn giống nhau ở cả hai frame
        for idx in (2, 8):
            self._gt(gt_dir, idx, gt)
            self._pred(pred_dir, idx, phu_kin)
        frames = [{"frame_idx": 2, "pred_path": str(pred_dir / "mask_000002.png")},
                  {"frame_idx": 8, "pred_path": str(pred_dir / "mask_000008.png")}]
        kq = sm.cham(frames, gt_dir)
        assert kq["mask_ngoai_gt_max_frame"] == 2
        kq_nguoc = sm.cham(list(reversed(frames)), gt_dir)          # đảo thứ tự index
        assert kq_nguoc["mask_ngoai_gt_max_frame"] == 2, "hoà phải xác định, không phụ thuộc thứ tự"
        assert kq_nguoc["mask_ngoai_gt_max"] == kq["mask_ngoai_gt_max"]


class TestAnhGtCoAlpha:
    """GT xuất từ trình duyệt/Paint.NET là PNG **4 kênh**; alpha 255 khắp nơi không được thành
    "GT phủ kín khung" (đã xảy ra 15-11 với công cụ vẽ trong trình duyệt: 100 % khung)."""

    def test_alpha_duc_khong_lam_gt_thanh_toan_khung(self, tmp_path):
        import cv2

        rgba = np.zeros((20, 10, 4), np.uint8)
        rgba[5:15, 3:7, :3] = 255
        rgba[:, :, 3] = 255
        cv2.imwrite(str(tmp_path / "gt_000000.png"), rgba)
        mask = sm.doc_mask(tmp_path / "gt_000000.png")
        assert mask.shape == (20, 10)
        assert int(mask.sum()) == 10 * 4


class TestKiemIndex:
    def _index(self, tmp_path, **kw):
        base = {"clip": "data/binh1.mp4", "nguoi_gan": "Bình", "dang_gt": "silhouette",
                "gt_do_model_goi_y": False, "frames": [{"frame_idx": 0}]}
        base.update(kw)
        return base

    def test_hop_le(self, tmp_path):
        import cv2

        cv2.imwrite(str(tmp_path / "gt_000000.png"), np.full((4, 4), 255, np.uint8))
        assert sm.kiem_index(self._index(tmp_path), tmp_path) == ([], [])

    # ── `dang_gt`: HÌNH DẠNG của GT (15-11) ──────────────────────────────────────────────
    def test_hop_bao_la_canh_bao_mem_kem_nghia(self, tmp_path):
        """GT hộp bao vẫn CHẤM được, nhưng artifact/phải nói rõ đây KHÔNG phải mIoU phân đoạn."""
        import cv2

        cv2.imwrite(str(tmp_path / "gt_000000.png"), np.full((4, 4), 255, np.uint8))
        chan, mem = sm.kiem_index(self._index(tmp_path, dang_gt="hop_bao"), tmp_path)
        assert not chan
        assert any("HỘP BAO" in x and "KHÔNG phải mIoU phân đoạn" in x for x in mem)

    def test_khong_khai_bao_dang_gt_la_canh_bao(self, tmp_path):
        """GT cũ chưa có khoá này: không chặn, nhưng phải nói "không biết là dạng gì"."""
        import cv2

        cv2.imwrite(str(tmp_path / "gt_000000.png"), np.full((4, 4), 255, np.uint8))
        idx = self._index(tmp_path)
        idx.pop("dang_gt")
        chan, mem = sm.kiem_index(idx, tmp_path)
        assert not chan and any("dang_gt" in x for x in mem)

    def test_dang_gt_la_bi_canh_bao(self, tmp_path):
        import cv2

        cv2.imwrite(str(tmp_path / "gt_000000.png"), np.full((4, 4), 255, np.uint8))
        _chan, mem = sm.kiem_index(self._index(tmp_path, dang_gt="gi_do"), tmp_path)
        assert any("lạ" in x for x in mem)

    def test_file_gt_byte_rac_la_LOI_chan(self, tmp_path):
        """`is_file()` không đủ: một file 1 byte từng được "chứng nhận hợp lệ" trong khi `score` sẽ
        chết vì không giải mã được (review hẹp 14-11, P2)."""
        (tmp_path / "gt_000000.png").write_bytes(b"x")
        chan, _mem = sm.kiem_index(self._index(tmp_path), tmp_path)
        assert any("không đọc được" in x for x in chan)

    def test_gt_sai_kich_thuoc_la_LOI_chan(self, tmp_path):
        import cv2

        cv2.imwrite(str(tmp_path / "gt_000000.png"), np.full((4, 4), 255, np.uint8))
        chan, _mem = sm.kiem_index(self._index(tmp_path, frame_hw=[8, 8]), tmp_path)
        assert any("sai kích thước" in x for x in chan)

    def test_gt_toan_den_chi_la_canh_bao(self, tmp_path):
        import cv2

        cv2.imwrite(str(tmp_path / "gt_000000.png"), np.zeros((4, 4), np.uint8))
        chan, mem = sm.kiem_index(self._index(tmp_path), tmp_path)
        assert not chan and any("toàn đen" in x for x in mem)

    def test_thieu_file_gt_la_loi_CHAN(self, tmp_path):
        chan, _mem = sm.kiem_index(self._index(tmp_path), tmp_path)
        assert any("thiếu file GT" in x for x in chan)

    def test_thieu_nguoi_gan_chi_la_canh_bao_mem(self, tmp_path):
        import cv2

        cv2.imwrite(str(tmp_path / "gt_000000.png"), np.full((4, 4), 255, np.uint8))
        chan, mem = sm.kiem_index(self._index(tmp_path, nguoi_gan=""), tmp_path)
        assert not chan and any("nguoi_gan" in x for x in mem)

    def test_gt_do_model_goi_y_bi_TU_CHOI_chan(self, tmp_path):
        """Chấm mIoU trên mask do CHÍNH model sinh ra = đo chính nó, không phải đo chất lượng.

        P1 review 14-11: bản trước chỉ in cảnh báo rồi **vẫn chấm và trả 0** ⇒ "chốt chặn danh nghĩa".
        """
        import cv2

        cv2.imwrite(str(tmp_path / "gt_000000.png"), np.full((4, 4), 255, np.uint8))
        chan, _mem = sm.kiem_index(self._index(tmp_path, gt_do_model_goi_y=True), tmp_path)
        assert any("gợi ý" in x for x in chan)

    def test_frame_trung_va_am(self, tmp_path):
        (tmp_path / "gt_000000.png").write_bytes(b"x")
        chan, _mem = sm.kiem_index(self._index(tmp_path, frames=[{"frame_idx": 0}, {"frame_idx": 0},
                                                                {"frame_idx": -3}]), tmp_path)
        assert any("trùng" in x for x in chan) and any("không hợp lệ" in x for x in chan)

    def test_frames_rong(self, tmp_path):
        chan, _mem = sm.kiem_index(self._index(tmp_path, frames=[]), tmp_path)
        assert any("rỗng" in x for x in chan)

    # ── Cổng "GT hộp bao ↔ `hop_bao_xywh`" (ticket #30) ────────────────────────────────────
    def _gt_hop(self, tmp_path, idx, x, y, w, h, hw=(10, 10)):
        import cv2

        mask = np.zeros(hw, np.uint8)
        mask[y:y + h, x:x + w] = 255
        cv2.imwrite(str(tmp_path / f"gt_{idx:06d}.png"), mask)

    def test_hop_bao_khop_hop_xywh_thi_khong_chan(self, tmp_path):
        self._gt_hop(tmp_path, 0, 2, 3, 4, 5)
        chan, _mem = sm.kiem_index(
            self._index(tmp_path, dang_gt="hop_bao",
                        frames=[{"frame_idx": 0, "hop_bao_xywh": [2, 3, 4, 5]}]), tmp_path)
        assert not chan

    def test_hop_bao_sai_dien_tich_la_LOI_chan(self, tmp_path):
        """Đây là lớp lỗi "GT lẫn frame khác": mask 16 px trong khi hộp khai 4×4 = 16 px thì khớp,
        nên dùng mask 4×4 mà hộp 3×3 để chắc chắn lệch."""
        self._gt_hop(tmp_path, 0, 0, 0, 4, 4)
        chan, _mem = sm.kiem_index(
            self._index(tmp_path, dang_gt="hop_bao",
                        frames=[{"frame_idx": 0, "hop_bao_xywh": [0, 0, 3, 3]}]), tmp_path)
        assert any("hộp khai" in x and "lẫn frame khác" in x for x in chan)

    def test_hop_bao_sai_vi_tri_la_LOI_chan(self, tmp_path):
        """Cùng số pixel nhưng nằm chỗ khác ⇒ vẫn là GT sai (sum == w*h KHÔNG đủ)."""
        self._gt_hop(tmp_path, 0, 5, 5, 2, 2)
        chan, _mem = sm.kiem_index(
            self._index(tmp_path, dang_gt="hop_bao",
                        frames=[{"frame_idx": 0, "hop_bao_xywh": [0, 0, 2, 2]}]), tmp_path)
        assert any("không phải hình chữ nhật" in x for x in chan)

    def test_hop_bao_vuot_bien_khung_la_LOI_chan(self, tmp_path):
        self._gt_hop(tmp_path, 0, 0, 0, 2, 2)
        chan, _mem = sm.kiem_index(
            self._index(tmp_path, dang_gt="hop_bao",
                        frames=[{"frame_idx": 0, "hop_bao_xywh": [9, 9, 2, 2]}]), tmp_path)
        assert any("vượt biên khung" in x for x in chan)

    def test_hop_bao_xywh_dinh_dang_sai_la_LOI_chan(self, tmp_path):
        self._gt_hop(tmp_path, 0, 0, 0, 2, 2)
        for hop in ([0, 0, 0, 2], [0, 0, 2], [0, 0, 2.5, 2], [True, 0, 2, 2], "0,0,2,2"):
            chan, _mem = sm.kiem_index(
                self._index(tmp_path, dang_gt="hop_bao",
                            frames=[{"frame_idx": 0, "hop_bao_xywh": hop}]), tmp_path)
            assert any("hop_bao_xywh' không hợp lệ" in x for x in chan), hop

    def test_hop_bao_thieu_hop_xywh_chi_la_canh_bao(self, tmp_path):
        """Khai dạng hộp bao mà không có hộp ⇒ không đối chiếu được, nhưng KHÔNG chặn (GT cũ)."""
        self._gt_hop(tmp_path, 0, 0, 0, 2, 2)
        chan, mem = sm.kiem_index(self._index(tmp_path, dang_gt="hop_bao"), tmp_path)
        assert not chan and any("hop_bao_xywh" in x for x in mem)

    def test_hop_bao_xywh_khong_bi_kiem_khi_gt_silhouette(self, tmp_path):
        """Cổng này CHỈ áp cho `dang_gt = hop_bao`: GT silhouette có thể kèm hộp (chỉ để tham khảo)."""
        self._gt_hop(tmp_path, 0, 5, 5, 2, 2)
        chan, _mem = sm.kiem_index(
            self._index(tmp_path, dang_gt="silhouette",
                        frames=[{"frame_idx": 0, "hop_bao_xywh": [0, 0, 2, 2]}]), tmp_path)
        assert not chan

    def test_hop_bao_cham_mep_khung_khong_bi_chan(self, tmp_path):
        """Hộp chạm mép (x+w == W, y+h == H) là HỢP LỆ — chặn oan thì bộ GT thật (frame 72 có y=0)
        không chấm được (P3 review 16-11)."""
        self._gt_hop(tmp_path, 0, 6, 8, 4, 4, hw=(12, 10))   # khung 10 cột × 12 hàng, chạm cả 2 mép
        chan, _mem = sm.kiem_index(
            self._index(tmp_path, dang_gt="hop_bao",
                        frames=[{"frame_idx": 0, "hop_bao_xywh": [6, 8, 4, 4]}]), tmp_path)
        assert not chan

    def test_hop_bao_gt_rong_bao_dung_cach_sua_ro_rang(self, tmp_path):
        """Vật đã rời khung ⇒ GT rỗng là ĐÚNG; khai hộp cho frame rỗng là mâu thuẫn, và thông điệp
        phải chỉ cách sửa, không được để người chạy tưởng "GT lẫn frame khác" (P2 review 16-11)."""
        import cv2

        cv2.imwrite(str(tmp_path / "gt_000000.png"), np.zeros((10, 10), np.uint8))
        chan, _mem = sm.kiem_index(
            self._index(tmp_path, dang_gt="hop_bao",
                        frames=[{"frame_idx": 0, "hop_bao_xywh": [1, 1, 4, 4]}]), tmp_path)
        assert any("RỜI KHUNG" in x and "BỎ 'hop_bao_xywh'" in x for x in chan)
        assert not any("lẫn frame khác" in x for x in chan)

    def test_bo_gt_hop_bao_da_commit_phai_qua_cong(self):
        """Tiêu chí nghiệm thu ticket #30/#31: cổng mới KHÔNG được chặn OAN bộ GT đã commit (12 frame),
        và cũng KHÔNG được cảnh báo oan "CÙNG một hộp" (12 hộp đều khác nhau).

        Lưu ý: test này MỘT CHIỀU — nó chỉ canh "không chặn oan", không canh "cổng tồn tại" (phần đó
        do các test `..._la_LOI_chan` / `..._copy_paste` ở trên ghim).
        """
        gt_dir = sm.GT_DIR / "binh1_hopbao"
        index = json.loads((gt_dir / "index.json").read_text(encoding="utf-8"))
        chan, mem = sm.kiem_index(index, gt_dir)
        assert chan == []
        assert not any("CÙNG một hộp" in x for x in mem), mem

    def test_gt_rong_bo_hop_khong_bi_dem_la_thieu_hop(self, tmp_path):
        """Vật đã rời khung ⇒ GT rỗng + BỎ `hop_bao_xywh` là cách sửa ĐÚNG; không được cảnh báo
        "thêm hộp vào index" (hai câu khuyên ngược nhau — P3 review vòng 2)."""
        import cv2

        cv2.imwrite(str(tmp_path / "gt_000000.png"), np.zeros((10, 10), np.uint8))
        chan, mem = sm.kiem_index(self._index(tmp_path, dang_gt="hop_bao"), tmp_path)
        assert not chan
        assert not any("hop_bao_xywh" in x for x in mem), mem

    def test_hai_frame_cung_mot_hop_la_canh_bao_copy_paste(self, tmp_path):
        """Bản hộp bao của `DUP_IOU` (gt_check_silhouette): hai frame khai CÙNG hộp ⇒ nghi copy-paste.
        Cảnh báo MỀM (vật đứng yên vẫn có thể trùng hộp thật) — P3 review 16-11."""
        self._gt_hop(tmp_path, 0, 2, 3, 4, 5)
        self._gt_hop(tmp_path, 7, 2, 3, 4, 5)
        chan, mem = sm.kiem_index(
            self._index(tmp_path, dang_gt="hop_bao",
                        frames=[{"frame_idx": 0, "hop_bao_xywh": [2, 3, 4, 5]},
                                {"frame_idx": 7, "hop_bao_xywh": [2, 3, 4, 5]}]), tmp_path)
        assert not chan
        assert any("CÙNG một hộp" in x and "copy-paste" in x for x in mem), mem

    def test_hai_frame_hop_khac_nhau_thi_khong_canh_bao(self, tmp_path):
        self._gt_hop(tmp_path, 0, 2, 3, 4, 5)
        self._gt_hop(tmp_path, 7, 3, 3, 4, 5)
        _chan, mem = sm.kiem_index(
            self._index(tmp_path, dang_gt="hop_bao",
                        frames=[{"frame_idx": 0, "hop_bao_xywh": [2, 3, 4, 5]},
                                {"frame_idx": 7, "hop_bao_xywh": [3, 3, 4, 5]}]), tmp_path)
        assert not any("CÙNG một hộp" in x for x in mem), mem


class TestKiemKhopManifest:
    """GT và mask phải là CÙNG clip, CÙNG frame — `manifest.json` của thư mục mask là chỗ kiểm được
    điều đó (lớp lỗi "ghép GT với mask của frame khác", P0 14-11). Cảnh báo MỀM.
    """

    _idx = {"clip": "data/binh1.mp4", "frames": [{"frame_idx": 2}, {"frame_idx": 12}]}

    def test_khop_thi_khong_canh_bao(self):
        man = {"nguon": "data/binh1.mp4", "frames_yeu_cau": [2, 12]}
        assert sm.kiem_khop_manifest(self._idx, man) == []

    def test_clip_khac_nguon_la_canh_bao(self):
        man = {"nguon": "data/binh2.mp4", "frames_yeu_cau": [2, 12]}
        mem = sm.kiem_khop_manifest(self._idx, man)
        assert any("KHÁC nguồn của mask" in x for x in mem)

    def test_frame_ngoai_frames_yeu_cau_la_canh_bao(self):
        man = {"nguon": "data/binh1.mp4", "frames_yeu_cau": [2]}
        mem = sm.kiem_khop_manifest(self._idx, man)
        assert any("KHÔNG nằm trong `frames_yeu_cau`" in x and "12" in x for x in mem)

    def test_khong_co_manifest_thi_khong_doan(self):
        assert sm.kiem_khop_manifest(self._idx, None) == []
        assert sm.kiem_khop_manifest(self._idx, {"nguon": "data/binh1.mp4"}) == []

    def test_frames_yeu_cau_dang_chuoi_van_doi_chieu_duoc(self):
        """Manifest viết tay có thể ghi `"2,12"` — bỏ qua im lặng là fail-open (P3 review 16-11)."""
        assert sm.kiem_khop_manifest(self._idx, {"frames_yeu_cau": "2,12"}) == []
        mem = sm.kiem_khop_manifest({"clip": "x", "frames": [{"frame_idx": 5}]},
                                    {"frames_yeu_cau": "2,12"})
        assert any("KHÔNG nằm trong `frames_yeu_cau`" in x for x in mem)


class TestLabelKhongTuKhaiDangGt:
    """`label` sinh frame TRƯỚC khi người tô ⇒ không được khai `dang_gt = silhouette` (P1 review 15-11).

    Ca thật: người dùng vẽ **hộp** chứ không tô silhouette; index khai sẵn `silhouette` nên cảnh báo
    "GT hộp bao" không bao giờ in ra và artifact công bố số sai nghĩa với exit 0.
    """

    def _clip(self, tmp_path):
        import cv2

        clip = tmp_path / "c.mp4"
        w = cv2.VideoWriter(str(clip), cv2.VideoWriter_fourcc(*"mp4v"), 5, (32, 24))
        for _ in range(3):
            w.write(np.full((24, 32, 3), 90, np.uint8))
        w.release()
        return clip

    def test_khong_truyen_dang_gt_thi_index_de_none(self, tmp_path, monkeypatch):
        monkeypatch.setattr(sm, "GT_DIR", tmp_path)          # KHÔNG ghi vào docs/gt của repo
        clip = self._clip(tmp_path)
        gt = tmp_path / "x"
        assert sm.main(["label", "--clip", str(clip), "--frames", "0,2", "--ten", "x",
                        "--nguoi-gan", "Bình"]) == 0
        idx = json.loads((gt / "index.json").read_text(encoding="utf-8"))
        assert idx["dang_gt"] is None, "phải để người khai, không đoán hộ"
        assert idx["phuong_phap_gt"] is None

    def test_kiem_index_canh_bao_khi_chua_khai_dang_gt(self, tmp_path, monkeypatch):
        import cv2

        monkeypatch.setattr(sm, "GT_DIR", tmp_path)
        clip = self._clip(tmp_path)
        gt = tmp_path / "x"
        sm.main(["label", "--clip", str(clip), "--frames", "0", "--ten", "x", "--nguoi-gan", "B"])
        cv2.imwrite(str(gt / "gt_000000.png"), np.full((24, 32), 255, np.uint8))
        chan, mem = sm.kiem_index(json.loads((gt / "index.json").read_text(encoding="utf-8")), gt)
        assert not chan and any("dang_gt" in x for x in mem)

    def test_truyen_dang_gt_thi_index_ghi_dung(self, tmp_path, monkeypatch):
        monkeypatch.setattr(sm, "GT_DIR", tmp_path)
        clip = self._clip(tmp_path)
        gt = tmp_path / "x"
        sm.main(["label", "--clip", str(clip), "--frames", "1", "--ten", "x", "--nguoi-gan", "B",
                 "--dang-gt", "hop_bao", "--phuong-phap-gt", "ngưỡng màu"])
        idx = json.loads((gt / "index.json").read_text(encoding="utf-8"))
        assert idx["dang_gt"] == "hop_bao" and idx["phuong_phap_gt"] == "ngưỡng màu"


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

    def test_artifact_ghi_dang_gt_va_phuong_phap(self, tmp_path, monkeypatch):
        """Không ghi `dang_gt`/`phuong_phap_gt` thì người đọc artifact không biết "0,65" là
        mIoU phân đoạn hay IoU với hộp bao — đúng loại "số đúng nhưng gắn sai nghĩa"."""
        import cv2

        gt, pred = tmp_path / "gt", tmp_path / "pred"
        gt.mkdir()
        pred.mkdir()
        (gt / "index.json").write_text(json.dumps({
            "clip": "data/binh1.mp4", "nguoi_gan": "Bình", "dang_gt": "hop_bao",
            "phuong_phap_gt": "ngưỡng màu nhãn tím + sửa tay",
            "frames": [{"frame_idx": 0}]}), encoding="utf-8")
        cv2.imwrite(str(gt / "gt_000000.png"), np.full((4, 4), 255, np.uint8))
        cv2.imwrite(str(pred / "mask_000000.png"), np.full((4, 4), 255, np.uint8))
        out = gt / "art.json"
        import scripts.measure_watchdog as mw

        monkeypatch.setattr(mw, "_git_provenance", lambda: ("abc1234", False, False, None))
        ma = sm.main(["score", "--gt", str(gt), "--pred-dir", str(pred), "--out", str(out)])

        payload = json.loads(out.read_text(encoding="utf-8"))
        assert payload["meta"]["dang_gt"] == "hop_bao"
        assert "ngưỡng màu" in payload["meta"]["phuong_phap_gt"]
        # `grep mIoU` phải thấy cảnh báo NGAY CẠNH con số (ticket #30): không chỉ nằm trong `meta`.
        assert payload["ket_qua"]["gt_dang"] == "hop_bao"
        assert "KHÔNG phải mIoU phân đoạn" in payload["ket_qua"]["mIoU_dinh_nghia"]
        assert ma == 1, "cảnh báo mềm (GT hộp bao) ⇒ exit 1, không phải 0"

    def test_check_index_in_dang_gt_va_nguon_gt(self, tmp_path, capsys):
        """`--check-index` là chỗ người chạy hay xem nhất ⇒ phải in dạng GT + nguồn GT, không chỉ
        "hợp lệ" (ticket #30)."""
        import cv2

        gt = tmp_path / "gt"
        gt.mkdir()
        (gt / "index.json").write_text(json.dumps({
            "clip": "data/binh1.mp4", "nguoi_gan": "Bình", "dang_gt": "hop_bao",
            "nguon_gt": "ngưỡng màu HSV nhãn tím",
            "frames": [{"frame_idx": 0, "hop_bao_xywh": [1, 1, 2, 2]}],
            "frame_hw": [10, 10]}), encoding="utf-8")
        mask = np.zeros((10, 10), np.uint8)
        mask[1:3, 1:3] = 255
        cv2.imwrite(str(gt / "gt_000000.png"), mask)

        ma = sm.main(["score", "--gt", str(gt), "--pred-dir", str(tmp_path / "pred"),
                      "--check-index"])

        out = capsys.readouterr().out
        assert "dạng GT: hop_bao" in out and "HỘP BAO" in out
        assert "nguồn GT: ngưỡng màu HSV nhãn tím" in out
        assert ma == 1          # vẫn còn cảnh báo mềm "GT hộp bao"


class TestManifestHong:
    """"Có manifest nhưng HỎNG" phải KHÁC "không có manifest" — gộp hai ca thì cảnh báo mất nghĩa
    (P3 review 16-11)."""

    def test_khong_co_file_la_none_khong_loi(self, tmp_path):
        assert sm._doc_manifest(tmp_path) == (None, None)

    def test_json_hong_bao_loi(self, tmp_path):
        (tmp_path / "manifest.json").write_text("{không phải json", encoding="utf-8")
        man, loi = sm._doc_manifest(tmp_path)
        assert man is None and loi and "không đọc được" in loi

    def test_khong_phai_object_bao_loi(self, tmp_path):
        (tmp_path / "manifest.json").write_text("[1,2]", encoding="utf-8")
        man, loi = sm._doc_manifest(tmp_path)
        assert man is None and loi and "object JSON" in loi

    def test_score_ghi_loi_manifest_vao_artifact(self, tmp_path, monkeypatch):
        import cv2

        gt, pred = tmp_path / "gt", tmp_path / "pred"
        gt.mkdir()
        pred.mkdir()
        (gt / "index.json").write_text(json.dumps({
            "clip": "data/binh1.mp4", "nguoi_gan": "Bình", "dang_gt": "silhouette",
            "frames": [{"frame_idx": 0}]}), encoding="utf-8")
        cv2.imwrite(str(gt / "gt_000000.png"), np.full((4, 4), 255, np.uint8))
        cv2.imwrite(str(pred / "mask_000000.png"), np.full((4, 4), 255, np.uint8))
        (pred / "manifest.json").write_text("{hỏng", encoding="utf-8")
        out = tmp_path / "art.json"
        import scripts.measure_watchdog as mw

        monkeypatch.setattr(mw, "_git_provenance", lambda: ("abc1234", False, False, None))
        ma = sm.main(["score", "--gt", str(gt), "--pred-dir", str(pred), "--out", str(out)])

        payload = json.loads(out.read_text(encoding="utf-8"))
        assert payload["meta"]["mask_manifest"] is None
        assert payload["meta"]["mask_manifest_loi"]
        assert any("manifest của mask HỎNG" in x for x in payload["canh_bao_gt"])
        assert ma == 1

    def test_check_index_in_manifest_hong(self, tmp_path, capsys):
        import cv2

        gt, pred = tmp_path / "gt", tmp_path / "pred"
        gt.mkdir()
        pred.mkdir()
        (gt / "index.json").write_text(json.dumps({
            "clip": "data/binh1.mp4", "nguoi_gan": "Bình", "dang_gt": "silhouette",
            "frames": [{"frame_idx": 0}]}), encoding="utf-8")
        cv2.imwrite(str(gt / "gt_000000.png"), np.full((4, 4), 255, np.uint8))
        (pred / "manifest.json").write_text("[1,2]", encoding="utf-8")

        sm.main(["score", "--gt", str(gt), "--pred-dir", str(pred), "--check-index"])

        out = capsys.readouterr().out
        assert "manifest của mask HỎNG" in out
        # Ca HỎNG phải KHÁC ca "không có manifest": nếu ai revert nhánh `duoi` thì câu cũ vẫn xuất hiện
        # từ vòng in `mem` ⇒ test chỉ so chuỗi HỎNG sẽ XANH vô nghĩa (P2 review 16-11).
        assert "KHÔNG có manifest" not in out


    def test_manifest_hop_le_van_vao_artifact_duoi_dang_dict(self, tmp_path, monkeypatch):
        """Manifest HỢP LỆ vẫn phải vào `meta.mask_manifest` dạng dict và `mask_manifest_loi = None` —
        nếu ai gán nhầm cả tuple `(manifest, lỗi)` thì artifact thành `null` mà không test nào đỏ
        (P3 review 16-11)."""
        import cv2

        gt, pred = tmp_path / "gt", tmp_path / "pred"
        gt.mkdir()
        pred.mkdir()
        (gt / "index.json").write_text(json.dumps({
            "clip": "data/binh1.mp4", "nguoi_gan": "Bình", "dang_gt": "silhouette",
            "frames": [{"frame_idx": 0}]}), encoding="utf-8")
        cv2.imwrite(str(gt / "gt_000000.png"), np.full((4, 4), 255, np.uint8))
        cv2.imwrite(str(pred / "mask_000000.png"), np.full((4, 4), 255, np.uint8))
        (pred / "manifest.json").write_text(json.dumps({
            "nguon": "data/binh1.mp4", "frames_yeu_cau": [0], "image_size": 192}),
            encoding="utf-8")
        out = tmp_path / "art.json"
        import scripts.measure_watchdog as mw

        monkeypatch.setattr(mw, "_git_provenance", lambda: ("abc1234", False, False, None))
        sm.main(["score", "--gt", str(gt), "--pred-dir", str(pred), "--out", str(out)])

        meta = json.loads(out.read_text(encoding="utf-8"))["meta"]
        assert isinstance(meta["mask_manifest"], dict)
        assert meta["mask_manifest"]["nguon"] == "data/binh1.mp4"
        assert meta["mask_manifest_loi"] is None


class TestManifestDuocGoiTuMain:
    """`main()` phải THẬT SỰ gọi `kiem_khop_manifest` — xoá dòng gọi thì cảnh báo biến mất mà test nào
    cũng xanh (P2 review 16-11: "cổng danh nghĩa")."""

    def test_manifest_nguon_khac_thi_artifact_co_canh_bao(self, tmp_path, monkeypatch):
        import cv2

        gt, pred = tmp_path / "gt", tmp_path / "pred"
        gt.mkdir()
        pred.mkdir()
        (gt / "index.json").write_text(json.dumps({
            "clip": "data/binh1.mp4", "nguoi_gan": "Bình", "dang_gt": "silhouette",
            "frames": [{"frame_idx": 0}]}), encoding="utf-8")
        cv2.imwrite(str(gt / "gt_000000.png"), np.full((4, 4), 255, np.uint8))
        cv2.imwrite(str(pred / "mask_000000.png"), np.full((4, 4), 255, np.uint8))
        (pred / "manifest.json").write_text(json.dumps({
            "nguon": "data/binh2.mp4", "frames_yeu_cau": [0]}), encoding="utf-8")
        out = tmp_path / "art.json"
        import scripts.measure_watchdog as mw

        monkeypatch.setattr(mw, "_git_provenance", lambda: ("abc1234", False, False, None))
        ma = sm.main(["score", "--gt", str(gt), "--pred-dir", str(pred), "--out", str(out)])

        payload = json.loads(out.read_text(encoding="utf-8"))
        assert any("KHÁC nguồn của mask" in x for x in payload["canh_bao_gt"])
        assert ma == 1, "mIoU ghép hai clip khác nhau ⇒ phải exit 1"


class TestArtifactGtDang:
    def test_dang_gt_khong_khai_van_co_cau_dinh_nghia(self, tmp_path, monkeypatch):
        """`gt_dang = null` trông y hệt một bộ silhouette hợp lệ nếu không còn câu định nghĩa nào
        trong `ket_qua` ⇒ người đọc lại gọi con số là "mIoU phân đoạn" (P2 review 16-11)."""
        import cv2

        gt, pred = tmp_path / "gt", tmp_path / "pred"
        gt.mkdir()
        pred.mkdir()
        (gt / "index.json").write_text(json.dumps({
            "clip": "data/binh1.mp4", "nguoi_gan": "Bình",
            "frames": [{"frame_idx": 0}]}), encoding="utf-8")
        cv2.imwrite(str(gt / "gt_000000.png"), np.full((4, 4), 255, np.uint8))
        cv2.imwrite(str(pred / "mask_000000.png"), np.full((4, 4), 255, np.uint8))
        out = tmp_path / "art.json"
        import scripts.measure_watchdog as mw

        monkeypatch.setattr(mw, "_git_provenance", lambda: ("abc1234", False, False, None))
        sm.main(["score", "--gt", str(gt), "--pred-dir", str(pred), "--out", str(out)])

        payload = json.loads(out.read_text(encoding="utf-8"))
        assert payload["ket_qua"]["gt_dang"] is None
        assert "KHÔNG KHAI" in payload["ket_qua"]["mIoU_dinh_nghia"]
        # `gt_dang`/`mIoU_dinh_nghia` phải đứng TRƯỚC `mIoU` trong file (grep thấy cảnh báo trước số).
        khoa = list(payload["ket_qua"])
        assert khoa.index("mIoU_dinh_nghia") < khoa.index("mIoU")


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


class TestTuChoiChamKhiGtHong:
    """P1 review 14-11: lỗi GT chặn chấm phải làm script DỪNG (exit 2) và **không** ghi artifact."""

    def test_gt_do_model_goi_y_thi_exit_2_va_khong_ghi_artifact(self, tmp_path, capsys):
        import cv2

        gt = tmp_path / "gt"
        gt.mkdir()
        (gt / "index.json").write_text(json.dumps({
            "clip": "data/binh1.mp4", "nguoi_gan": "Bình", "gt_do_model_goi_y": True,
            "frames": [{"frame_idx": 0}]}), encoding="utf-8")
        cv2.imwrite(str(gt / "gt_000000.png"), np.full((4, 4), 255, np.uint8))
        pred = tmp_path / "pred"
        pred.mkdir()
        cv2.imwrite(str(pred / "mask_000000.png"), np.full((4, 4), 255, np.uint8))
        out = tmp_path / "art.json"

        ma = sm.main(["score", "--gt", str(gt), "--pred-dir", str(pred), "--out", str(out)])

        assert ma == 2, "GT do model gợi ý phải bị TỪ CHỐI chấm (không phải chỉ cảnh báo)"
        assert not out.exists(), "không được ghi artifact khi GT bị từ chối"
        assert "TỪ CHỐI CHẤM" in capsys.readouterr().out

    def test_thieu_file_gt_thi_exit_2(self, tmp_path):
        (tmp_path / "index.json").write_text(json.dumps({
            "clip": "x", "nguoi_gan": "B", "frames": [{"frame_idx": 3}]}), encoding="utf-8")
        assert sm.main(["score", "--gt", str(tmp_path), "--pred-dir", str(tmp_path),
                        "--out", str(tmp_path / "a.json")]) == 2
        assert not (tmp_path / "a.json").exists()
