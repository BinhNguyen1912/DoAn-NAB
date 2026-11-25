"""Test seam TrackerEngine — bọc SAMURAI thành streaming per-frame (ticket 02).

Nguyên tắc: chỉ test hành vi công khai của engine. Đáp án quỹ đạo lấy từ fixture
(synthetic square — nguồn độc lập), ngưỡng IoU quy định theo tiêu chí của ticket.
Chạy chậm (build model + propagation thật) — đánh dấu `slow`.
"""
import warnings

import numpy as np
import pytest

from src.synthetic_video import generate_tracking_sequence


def iou(box_a, box_b):
    """IoU 2 bbox (x1, y1, x2, y2) — cài đặt độc lập, không dựa vào code sản phẩm."""
    ax1, ay1, ax2, ay2 = box_a
    bx1, by1, bx2, by2 = box_b
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    inter = max(0, ix2 - ix1) * max(0, iy2 - iy1)
    area_a = max(0, ax2 - ax1) * max(0, ay2 - ay1)
    area_b = max(0, bx2 - bx1) * max(0, by2 - by1)
    union = area_a + area_b - inter
    return inter / union if union > 0 else 0.0


@pytest.mark.slow
class TestTrackerEngineStreaming:
    """Chuỗi test theo tiêu chí ticket 02 — chạy trên fixture giả lập."""

    def test_start_frame_0_mask_khong_rong_va_iou_dat_nguong(self, samurai_engine):
        """Tiêu chí 1 (phần start): frame 0 → mask không rỗng, bbox IoU ≥ 0.5."""
        fx = generate_tracking_sequence(num_frames=1, frame_size=(240, 320), square_size=40, start=(60, 60))
        res = samurai_engine.start(fx.frames[0], fx.bboxes[0])

        assert res.mask.shape == (240, 320)
        assert res.mask.dtype == bool
        assert res.mask.sum() > 0, "mask frame 0 không được rỗng ngay khi prompt chính xác"
        assert iou(res.bbox, fx.bboxes[0]) >= 0.5
        assert res.elapsed_ms > 0
        assert np.isfinite(res.score)

    def _chay_mot_lan(self, engine):
        """Chạy ĐÚNG kịch bản bám 10 frame ⇒ `(res0, results, fx)`; engine mới/reset trước khi gọi."""
        fx = generate_tracking_sequence(num_frames=10, frame_size=(240, 320), square_size=40, start=(60, 60))
        res0 = engine.start(fx.frames[0], fx.bboxes[0])
        results = [engine.process(fx.frames[i]) for i in range(1, 10)]
        return res0, results, fx

    # `pytest.ini` đặt `--timeout=120` chung; MỘT lượt kịch bản này đo được 44–74 s dưới tải ⇒ lượt
    # thứ hai (retry) có thể chạm 148 s và bị `pytest-timeout` giết TRƯỚC khi có kết quả, biến test
    # thành "Timeout >120.0s" thay vì message IoU (P1 review độc lập 17-11). Marker override `--timeout`.
    @pytest.mark.timeout(300)
    def test_process_theo_frames_iou_dat_o_cac_frame_mau(self, samurai_engine):
        """Tiêu chí 1 (phần process): feed 10 frame giả lập → bbox theo quỹ đạo, IoU ≥ 0.5.

        Chạy LẠI MỘT lần khi lần đầu dưới ngưỡng (ticket #22): test này từng ĐỎ trong `./run testall`
        ngày 10-11 mà xanh khi chạy riêng, và `AGENTS.md` §6 ghi **SAM 2 không tất định**. Đo trên máy
        này (`scripts/measure_flaky_iou.py`, 5 lần trên cây sạch, 17-11): IoU ở các frame mẫu
        **0,9506–0,9750**, và **cổng mà test này chấm** (min trên {0, 2, 5, 9}) là **0,9506** ⇒ cách
        ngưỡng 0,5 khoảng **0,45** (gấp ~33 lần độ lệch lớn nhất đo được của một frame, n = 5) ⇒ ngưỡng
        0,5 KHÔNG bị nới. Frame tệ nhất của CẢ 10 frame là 0,928 — nhưng đó là **frame 4, ngoài cổng**,
        đừng trích nó làm "cổng test" (P1 review 17-11). Phân bố trong cùng một tiến trình gần như tất định
        (f2/f9 `std = 0,0000`) ⇒ **chưa** đo được tính không tất định giữa các phiên; một lần đỏ là
        "chưa tái hiện được", không phải "đã chứng minh là ngoại lệ ngẫu nhiên".

        Điều kiện để test còn "có răng": nếu CẢ HAI lần đều dưới ngưỡng thì vẫn ĐỎ, và message nêu
        IoU của cả hai lần ⇒ hồi quy **ổn định** (mask trôi ở mọi lần) vẫn bị bắt. KHÔNG bảo đảm bắt
        hồi quy **gián đoạn**: retry 1 lần cho một hồi quy có xác suất đỏ p mỗi lần lọt với xác suất
        `1 - p²` (p = 0,5 ⇒ 75 % xanh) — vì thế lần 1 dưới ngưỡng được ghi lại bằng `warnings.warn`
        để còn dấu vết trong output của pytest (P2 review 17-11).
        """
        res0, results, fx = self._chay_mot_lan(samurai_engine)
        iou_lan_1 = {i: float(iou(results[i - 1].bbox, fx.bboxes[i])) for i in (2, 5, 9)}
        iou_lan_1[0] = float(iou(res0.bbox, fx.bboxes[0]))
        if min(iou_lan_1.values()) < 0.5:
            # Vẫn xanh nếu lần 2 đạt, nhưng KHÔNG im lặng: warning giữ lại giá trị lần 1 để một hồi
            # quy gián đoạn còn dấu vết trong log `./run testall`.
            warnings.warn(f"lần 1 dưới ngưỡng 0,5: {iou_lan_1} — chạy lại một lần", stacklevel=2)
            samurai_engine.reset()
            res0, results, fx = self._chay_mot_lan(samurai_engine)
            iou_lan_2 = {i: float(iou(results[i - 1].bbox, fx.bboxes[i])) for i in (2, 5, 9)}
            iou_lan_2[0] = float(iou(res0.bbox, fx.bboxes[0]))
            assert min(iou_lan_2.values()) >= 0.5, (
                f"Hai lần chạy liên tiếp đều dưới ngưỡng 0,5 ⇒ nghi hồi quy THẬT (không loại trừ được "
                f"nhiễu giữa phiên: lần đo 17-11 chỉ chạy trong MỘT tiến trình, chưa đo tính tất định "
                f"giữa các phiên): lần 1 {iou_lan_1}, lần 2 {iou_lan_2}")

        # Khoảng trống giữa bbox trả về và đáp án phải nhỏ (nhớ theo index: frames[i-1] trong results)
        for i in (2, 5, 9):
            res = results[i - 1]
            assert res.frame_idx == i
            assert res.mask.shape == (240, 320)
            assert res.elapsed_ms > 0
            assert np.isfinite(res.score)
            assert iou(res.bbox, fx.bboxes[i]) >= 0.5, f"IoU tại frame {i} thấp hơn ngưỡng"

    def test_frame_bi_che_khong_crash_va_ket_qua_hop_le(self, samurai_engine):
        """Tiêu chí 2: đố bị che khuất 2 frame → engine không crash, trả kết quả hợp lệ."""
        fx = generate_tracking_sequence(
            num_frames=8, frame_size=(240, 320), square_size=40, start=(60, 60), occlusion_frames=(3, 4)
        )
        engine = samurai_engine
        engine.start(fx.frames[0], fx.bboxes[0])

        for i in range(1, 8):
            res = engine.process(fx.frames[i])  # frame 3, 4 bị che — không được ném exception
            assert res.frame_idx == i
            assert res.mask.shape == (240, 320)
            assert res.mask.dtype == bool
            assert np.isfinite(res.score)
            if not fx.occluded[i]:
                # Trước/sau che khuất, mask có thể rỗng (hệ thống dừng track) nhưng phải là hợp lệ
                # — ở đây ô xuất hiện lại cùng vị trí quỹ đạo nên kỳ vọng bám lại tốt
                if res.mask.sum() > 0:
                    assert iou(res.bbox, fx.bboxes[i]) >= 0.3, (
                        f"frame {i} (ngoài che khuất) bám lại yếu: IoU < 0.3"
                    )

class TestImageSizeOverride:
    """Giảm `image_size` của SAM 2 để nhanh hơn trên CPU (đo thật 18-10).

    Fixture 20 frame (ô vuông + che 5 frame): 1024 → 5492 ms/frame IoU-sau-che 0.981;
    512 → 733 ms (1.36 FPS) IoU 0.988; 512 + re-anchor 3 → 558 ms (1.79 FPS) IoU 0.977.
    """

    def test_khong_truyen_thi_khong_override(self):
        from src.tracker_engine import build_overrides

        assert build_overrides(None) == []
        assert build_overrides(0) == []

    def test_truyen_so_thi_tao_override_hydra(self):
        from src.tracker_engine import build_overrides

        assert build_overrides(512) == ["++model.image_size=512"]
        assert build_overrides(768) == ["++model.image_size=768"]


class TestNguongMask:
    """`--mask-threshold`: ngưỡng logit để cắt phần rìa mờ (tóc, viền) khỏi mask.

    Mặc định 0.0 = lấy toàn bộ vùng model cho là đối tượng (dễ "ăn" tóc).
    Nâng lên 0.5–2.0 = chỉ giữ phần model TỰ TIN, mask co lại quanh vùng chắc chắn.
    """

    def test_nguong_0_lay_moi_pixel_duong(self):
        import torch

        from src.tracker_engine import TrackerEngine

        logits = torch.tensor([[[-2.0, 0.1], [0.5, 3.0]]])      # (1,H,W) như propagate trả
        mask, _ = TrackerEngine._mask_to_bbox(logits, threshold=0.0)
        assert mask.sum() == 3          # bỏ -2.0, giữ 0.1 / 0.5 / 3.0

    def test_nguong_cao_chi_giu_phan_tu_tin(self):
        import torch

        from src.tracker_engine import TrackerEngine

        logits = torch.tensor([[[-2.0, 0.1], [0.5, 3.0]]])      # (1,H,W) như propagate trả
        mask, bbox = TrackerEngine._mask_to_bbox(logits, threshold=1.0)
        assert mask.sum() == 1          # chỉ còn logit 3.0
        assert bbox == (1, 1, 1, 1)

    def test_nguong_qua_cao_mask_rong_bbox_0(self):
        import torch

        from src.tracker_engine import TrackerEngine

        logits = torch.tensor([[[-2.0, 0.1], [0.5, 0.9]]])
        mask, bbox = TrackerEngine._mask_to_bbox(logits, threshold=5.0)
        assert mask.sum() == 0 and bbox == (0, 0, 0, 0)


class TestStartPointsAndLabels:
    """Prompt điểm âm/dương (positive/negative) hỗ trợ bám vật thể ít texture/trắng trơn."""

    def _make_mock_engine(self):
        from unittest.mock import MagicMock
        import torch
        from src.tracker_engine import TrackerEngine

        predictor = MagicMock()
        tensor0 = torch.zeros((3, 64, 64), dtype=torch.float32)
        mock_state = {
            "images": [tensor0],
            "video_height": 64,
            "video_width": 64,
            "output_dict": {
                "cond_frame_outputs": {0: {"object_score_logits": [2.5]}},
                "non_cond_frame_outputs": {},
            },
        }
        predictor.init_state.return_value = mock_state
        video_res_masks = torch.ones((1, 1, 64, 64), dtype=torch.float32)
        predictor.propagate_in_video.return_value = iter([(0, [0], video_res_masks)])
        engine = TrackerEngine(predictor)
        return engine, predictor

    def test_start_truyen_points_va_labels_sang_predictor(self):
        import numpy as np
        engine, predictor = self._make_mock_engine()
        frame = np.zeros((64, 64, 3), dtype=np.uint8)
        points = [(30.0, 32.0), (10.0, 15.0)]
        labels = [1, 0]

        res = engine.start(frame, (10, 10, 50, 50), points=points, labels=labels)
        assert res.mask.shape == (64, 64)
        call_kwargs = predictor.add_new_points_or_box.call_args.kwargs
        assert call_kwargs.get("box") == (10, 10, 50, 50)
        assert np.allclose(call_kwargs.get("points"), points)
        assert list(call_kwargs.get("labels")) == labels

    def test_start_loi_khi_points_va_labels_khong_dong_bo(self):
        import numpy as np
        import pytest
        engine, _ = self._make_mock_engine()
        frame = np.zeros((64, 64, 3), dtype=np.uint8)

        # points có mà labels None
        with pytest.raises(ValueError, match="points và labels"):
            engine.start(frame, (10, 10, 50, 50), points=[(30.0, 32.0)])

        # số lượng lệch nhau
        with pytest.raises(ValueError, match="số lượng"):
            engine.start(frame, (10, 10, 50, 50), points=[(30.0, 32.0)], labels=[1, 0])

        # label không hợp lệ (không phải 0 hoặc 1)
        with pytest.raises(ValueError, match="label"):
            engine.start(frame, (10, 10, 50, 50), points=[(30.0, 32.0)], labels=[2])

        # point ngoài kích thước ảnh
        with pytest.raises(ValueError, match="ngoài khung"):
            engine.start(frame, (10, 10, 50, 50), points=[(100.0, 32.0)], labels=[1])

    def test_fixture_vat_trang_tren_nen_sang_khong_tran_mask(self):
        """Vật thể trắng (255) trên nền sáng (230): prompt điểm âm ở nền chặn tràn mask."""
        import numpy as np
        import torch
        from src.tracker_engine import TrackerEngine
        from unittest.mock import MagicMock

        predictor = MagicMock()
        mock_state = {
            "images": [torch.zeros((3, 64, 64), dtype=torch.float32)],
            "video_height": 64,
            "video_width": 64,
            "output_dict": {
                "cond_frame_outputs": {0: {"object_score_logits": [3.0]}},
                "non_cond_frame_outputs": {},
            },
        }
        predictor.init_state.return_value = mock_state

        # Giả lập mask: chỉ vùng đối tượng (20:44, 20:44) có logit dương
        logits = torch.full((1, 1, 64, 64), -5.0, dtype=torch.float32)
        logits[0, 0, 20:44, 20:44] = 3.0
        predictor.propagate_in_video.return_value = iter([(0, [0], logits)])

        engine = TrackerEngine(predictor)
        frame = np.full((64, 64, 3), 230, dtype=np.uint8)
        frame[20:44, 20:44] = 255  # vật trắng

        pts = [(32.0, 32.0), (10.0, 10.0), (55.0, 55.0)]
        lbls = [1, 0, 0]  # 1 positive ở tâm, 2 negative ở nền ngoài
        res = engine.start(frame, (20, 20, 44, 44), points=pts, labels=lbls)

        # Kiểm tra mask không tràn ra nền bên ngoài
        assert res.mask.shape == (64, 64)
        assert res.mask[0:15, 0:15].sum() == 0, "mask không được tràn ra nền góc ngoài"
        assert res.mask[20:44, 20:44].all(), "mask phải phủ kín vùng vật thể"
        assert res.bbox == (20, 20, 43, 43)



class TestBuildOverridesGate:
    """Plan 24-11 P2 — `min_obj_score_logits` phải đi qua **hydra override**, không copy config.

    Copy file config đã đo được là làm ĐỔI hành vi (cùng nội dung: mIoU 0,6987 → 0,2486) ⇒ mọi thí nghiệm
    đổi cấu hình model phải đi qua `build_overrides()`.
    """

    def test_mac_dinh_khong_them_override(self):
        from src.tracker_engine import build_overrides
        assert build_overrides(192) == ["++model.image_size=192"]
        assert build_overrides(192, None) == ["++model.image_size=192"]

    def test_co_nguong_thi_them_dong_override(self):
        from src.tracker_engine import build_overrides
        assert build_overrides(192, 0) == ["++model.image_size=192", "++model.min_obj_score_logits=0"]
        assert build_overrides(None, -100) == ["++model.min_obj_score_logits=-100"]


class TestModelOverrides:
    """Siêu tham số motion-memory của SAMURAI: khoá lạ phải NÉM, không được để hydra bỏ qua im lặng."""

    def test_dung_dinh_dang_hydra(self):
        from src.tracker_engine import build_overrides

        ra = build_overrides(192, None, {"kf_score_weight": 0.5, "samurai_mode": False,
                                         "stable_frames_threshold": 8})
        assert ra == ["++model.image_size=192", "++model.kf_score_weight=0.5",
                      "++model.samurai_mode=False", "++model.stable_frames_threshold=8"]

    def test_khoa_la_thi_nem(self):
        import pytest

        from src.tracker_engine import build_overrides

        with pytest.raises(ValueError, match="danh sách trắng"):
            build_overrides(192, None, {"kf_score_weigth": 0.5})   # typo thật

    def test_khong_doi_hanh_vi_khi_khong_truyen(self):
        from src.tracker_engine import build_overrides

        assert build_overrides(192, None, None) == ["++model.image_size=192"]

    def test_moi_khoa_trong_danh_sach_trang_deu_dinh_dang_duoc(self):
        from src.tracker_engine import MODEL_OVERRIDE_CHO_PHEP, build_overrides

        for key, loai in MODEL_OVERRIDE_CHO_PHEP.items():
            gia = True if loai is bool else (8 if loai is int else 0.5)
            ra = build_overrides(None, None, {key: gia})
            assert ra and ra[0].startswith(f"++model.{key}="), key
            assert "'" not in ra[0], f"{key}: repr lọt dấu nháy ⇒ hydra parse sai"


class TestXoaKalmanGiuaHaiPhien:
    """25-11: trạng thái **Kalman của SAMURAI** nằm trên MODEL, không thuộc `inference_state`.

    Đo trên máy này (13 frame `data/binh1.mp4`, cùng engine, cùng ô `(300,275,450,685)`):
    phiên 2 chạy ngay sau phiên 1 **lệch từ frame thứ 6**, `IoU` xuống **0,8253**; zero 3 field
    `kf_mean`/`kf_covariance`/`stable_frames` ⇒ **13/13 frame IoU = 1,0000**.

    Hệ quả người dùng thấy: bấm `r` chọn **vật khác** trong cùng phiên ⇒ Kalman mồi từ vật CŨ.
    """

    def test_ham_xoa_3_field_tren_predictor_gia(self):
        """Test NHANH (không cần model): hàm phải zero đúng 3 field và báo `True`."""
        from types import SimpleNamespace

        from src.tracker_engine import TrackerEngine

        gia = SimpleNamespace(kf_mean="x", kf_covariance="y", stable_frames=7, khac=1)
        eng = TrackerEngine.__new__(TrackerEngine)
        eng._predictor = gia
        assert eng._xoa_trang_thai_kalman() is True
        assert gia.kf_mean is None and gia.kf_covariance is None and gia.stable_frames == 0
        assert gia.khac == 1, "không được đụng field khác"

    def test_engine_khong_co_predictor_thi_khong_no(self):
        from src.tracker_engine import TrackerEngine

        eng = TrackerEngine.__new__(TrackerEngine)
        assert eng._xoa_trang_thai_kalman() is False

    @pytest.mark.slow
    # 26 lượt propagate ở image_size 1024 (fixture `samurai_engine` dựng mặc định) trên CPU vượt
    # hạn 120 s của `pytest.ini` ⇒ nới cho riêng test này (chỉ chạy trong `./run testall`).
    @pytest.mark.timeout(900)
    def test_hai_phien_lien_tiep_cho_mask_giong_tuyet_doi(self, samurai_engine):
        """Test KHOÁ hành vi thật (cần checkpoint + clip `data/binh1.mp4`, KHÔNG commit).

        Thiếu clip ⇒ skip (CI không có video — bài học 25-11: test phụ thuộc file không commit làm
        CI đỏ suốt 3 ngày).
        """
        import os

        import cv2

        clip = "data/binh1.mp4"
        if not os.path.isfile(clip):
            pytest.skip("cần data/binh1.mp4 (video KHÔNG commit)")

        cap = cv2.VideoCapture(clip)
        frames = []
        # Đo được: lệch bắt đầu từ frame thứ 6 (13 frame ⇒ min IoU 0,8253). 8 frame là đủ để bắt,
        # và giảm một nửa thời gian so với 13 (mỗi lượt propagate ~0,5 s ở 1024 trên CPU).
        while len(frames) < 8:
            ok, f = cap.read()
            if not ok:
                break
            frames.append(f)
        cap.release()
        if len(frames) < 8:
            pytest.skip("clip quá ngắn")
        box = (300, 275, 450, 685)

        def chay():
            out = []
            for i, f in enumerate(frames):
                r = samurai_engine.start(f, box) if i == 0 else samurai_engine.process(f)
                out.append(r.mask)
            return out

        lan1 = chay()
        lan2 = chay()
        for i, (a, b) in enumerate(zip(lan1, lan2)):
            inter = np.logical_and(a, b).sum()
            union = np.logical_or(a, b).sum()
            iou_mask = 1.0 if union == 0 else float(inter / union)
            assert iou_mask >= 0.999, (
                f"frame {i}: hai phiên liên tiếp lệch (IoU {iou_mask:.4f}) ⇒ Kalman rò giữa phiên; "
                "`start()` phải gọi `_xoa_trang_thai_kalman()`")
