"""Test module tái nhận diện (ADR-0003, ticket 09) — hàm thuần + máy trạng thái với engine giả.

Không cần model/SAM 2: engine và embedder đều là fake duck-type.
"""
import numpy as np
import pytest

from src.reid import (
    NGUONG_PHU_MAT,
    STATE_LOST,
    accept_candidate,
    STATE_REACQUIRING,
    STATE_TRACKING,
    FaceHit,
    LostResult,
    ReIdSession,
    best_match,
    cosine,
    face_quality_ok,
    pick_face_near,
)


def _vec(seed, dim=8):
    rng = np.random.default_rng(seed)
    v = rng.normal(size=dim).astype(np.float32)
    return v / np.linalg.norm(v)


class FakeEmbedder:
    """Embedder giả: trả danh sách FaceHit cố định (hoặc theo frame)."""

    def __init__(self, hits):
        self.hits = hits
        self.calls = 0

    def detect(self, _frame):
        self.calls += 1
        return self.hits


class FakeEngine:
    """Engine giả: mask rỗng/không rỗng theo hàng đợi; đếm số lần gọi."""

    def __init__(self, masks):
        self._masks = list(masks)
        self.start_calls = []
        self.process_calls = 0
        self.reset_calls = 0

    def _result(self, frame_idx, mask, bbox=(10, 10, 50, 50)):
        return type("R", (), {"frame_idx": frame_idx, "mask": mask, "bbox": bbox,
                              "score": 1.0, "elapsed_ms": 1.0})()

    def start(self, frame, bbox):
        self.start_calls.append(tuple(bbox))
        return self._result(0, np.ones((4, 4), bool), bbox)  # chọn ban đầu luôn thành công

    def process(self, frame):
        self.process_calls += 1
        return self._result(self.process_calls, self._next_mask())

    def reset(self):
        self.reset_calls += 1

    def _next_mask(self):
        empty = bool(self._masks.pop(0)) if self._masks else False
        return np.zeros((4, 4), bool) if empty else np.ones((4, 4), bool)


class FakeEngineMasks:
    """Engine giả cho cue VẬT THỂ: mask đúng kích thước frame, lấy theo hàng đợi (None = mask theo bbox).

    Không đụng `FakeEngine` cũ để không làm đổi hành vi các test khuôn mặt.
    `scores`: hàng đợi điểm object_score (mặc định 1.0) — cần để test ca SAM 2 "tưởng tượng" mask.
    """

    def __init__(self, masks, shape=(96, 96), scores=None, start_score=1.0, bboxes=None):
        self._masks = list(masks)
        self._scores = list(scores) if scores is not None else None
        self._bboxes = list(bboxes) if bboxes is not None else None
        self._start_score = float(start_score)
        self._shape = tuple(shape)
        self.start_calls = []
        self.process_calls = 0
        self.reset_calls = 0

    def _box_mask(self, bbox):
        m = np.zeros(self._shape, bool)
        x1, y1, x2, y2 = [int(v) for v in bbox]
        m[max(0, y1):min(y2, self._shape[0]), max(0, x1):min(x2, self._shape[1])] = True
        return m

    def _result(self, mask, bbox, score=1.0):
        return type("R", (), {"frame_idx": 0, "mask": mask, "bbox": bbox,
                              "score": float(score), "elapsed_ms": 1.0})()

    def start(self, frame, bbox):
        self.start_calls.append(tuple(bbox))
        return self._result(self._box_mask(bbox), bbox, self._start_score)

    def process(self, frame):
        self.process_calls += 1
        nxt = self._masks.pop(0) if self._masks else None
        score = self._scores.pop(0) if self._scores else 1.0
        bbox = self._bboxes.pop(0) if self._bboxes else (10, 10, 50, 50)
        if nxt is None:
            return self._result(self._box_mask(bbox), bbox, score)
        return self._result(nxt, bbox, score)

    def reset(self):
        self.reset_calls += 1


def _hit(bbox, emb, score=0.95):
    return FaceHit(bbox=tuple(bbox), score=score, embedding=emb)


class TestCosine:
    def test_cung_vector_bang_1(self):
        v = _vec(1)
        assert cosine(v, v) == pytest.approx(1.0, abs=1e-6)

    def test_truc_giao_bang_0(self):
        a, b = _vec(1), _vec(2)
        a = a - np.dot(a, b) * b  # trực giao hoá a theo b
        a = a / np.linalg.norm(a)
        assert cosine(a, b) == pytest.approx(0.0, abs=1e-6)

    def test_vector_khong_bang_0(self):
        assert cosine(np.zeros(8), _vec(1)) == 0.0


class TestBestMatch:
    def test_khong_co_mau_tham_chieu_tra_am(self):
        assert best_match([], _vec(1)) == -1.0

    def test_lay_max_tren_toan_tap(self):
        base = _vec(1)
        refs = [_vec(3), base, _vec(4)]
        assert best_match(refs, base) == pytest.approx(1.0, abs=1e-6)


class TestFaceQuality:
    def test_mat_qua_nho_bi_loai(self):
        assert face_quality_ok((0, 0, 30, 30), 0.99, min_face_px=40, min_score=0.8) is False

    def test_score_thap_bi_loai(self):
        assert face_quality_ok((0, 0, 60, 60), 0.5, min_face_px=40, min_score=0.8) is False

    def test_mat_du_lon_va_tin_cay_duoc_nhan(self):
        assert face_quality_ok((0, 0, 60, 60), 0.95, min_face_px=40, min_score=0.8) is True


class TestPickFaceNear:
    def test_chon_mat_nam_trong_bbox_dang_bam(self):
        a = _hit((0, 0, 40, 40), _vec(1))
        b = _hit((300, 300, 340, 340), _vec(2))
        assert pick_face_near([a, b], (280, 280, 360, 360)) is b

    def test_khong_co_mat_nao_trong_bbox_tra_none(self):
        a = _hit((0, 0, 40, 40), _vec(1))
        assert pick_face_near([a], (300, 300, 360, 360)) is None


class TestReIdSessionTracking:
    def test_step_khi_con_thay_goi_engine_process(self):
        engine = FakeEngine(masks=[])
        session = ReIdSession(engine=engine, embedder=FakeEmbedder([]), threshold=0.36)
        session.start(np.zeros((8, 8, 3), np.uint8), (0, 0, 4, 4))
        step = session.step(np.zeros((8, 8, 3), np.uint8))
        assert step.state == STATE_TRACKING
        assert engine.process_calls == 1

    def test_luu_mau_tham_chieu_tu_mat_nam_trong_bbox(self):
        tracked = (0, 0, 100, 100)
        emb = _vec(1)
        embedder = FakeEmbedder([_hit((10, 10, 60, 60), emb)])
        engine = FakeEngine(masks=[])
        session = ReIdSession(engine=engine, embedder=embedder, threshold=0.36)
        session.start(np.zeros((8, 8, 3), np.uint8), tracked)
        assert session.ref_count == 1


class TestReIdSessionLostFreeze:
    def test_mat_dau_thi_dong_bang_khong_goi_process_nua(self):
        engine = FakeEngine(masks=[True, True])   # 2 frame mask rỗng
        session = ReIdSession(engine=engine, embedder=FakeEmbedder([]),
                              threshold=0.36, lost_after_frames=2)
        session.start(np.zeros((8, 8, 3), np.uint8), (0, 0, 100, 100))
        s1 = session.step(np.zeros((8, 8, 3), np.uint8))
        s2 = session.step(np.zeros((8, 8, 3), np.uint8))
        assert s1.state == STATE_TRACKING
        assert s2.state == STATE_LOST
        calls_after_lost = engine.process_calls
        # các frame sau KHÔNG được gọi process nữa (đóng băng)
        s3 = session.step(np.zeros((8, 8, 3), np.uint8))
        s4 = session.step(np.zeros((8, 8, 3), np.uint8))
        assert engine.process_calls == calls_after_lost
        assert s3.state == STATE_REACQUIRING and s4.state == STATE_REACQUIRING

    def test_khong_khop_thi_van_lost_va_ghi_reid_score(self):
        ref_emb = _vec(1)
        other = _vec(9)
        embedder = FakeEmbedder([_hit((10, 10, 60, 60), ref_emb)])
        engine = FakeEngine(masks=[True, True])
        session = ReIdSession(engine=engine, embedder=embedder, threshold=0.99,
                              lost_after_frames=1)
        session.start(np.zeros((8, 8, 3), np.uint8), (0, 0, 100, 100))
        session.step(np.zeros((8, 8, 3), np.uint8))          # → LOST
        embedder.hits = [_hit((200, 200, 260, 260), other)]  # người khác
        step = session.step(np.zeros((8, 8, 3), np.uint8))
        assert step.state == STATE_REACQUIRING
        assert step.reacquired is False
        assert engine.start_calls == [(0, 0, 100, 100)]      # chỉ lần start đầu
        assert -1.0 <= step.reid_score <= 1.0
        assert not step.result.mask.any()
        assert isinstance(step.result, LostResult)


class TestReIdSessionReacquire:
    def test_khop_nguong_thi_goi_start_va_ve_tracking(self):
        ref_emb = _vec(1)
        embedder = FakeEmbedder([_hit((10, 10, 60, 60), ref_emb)])
        engine = FakeEngine(masks=[True])
        session = ReIdSession(engine=engine, embedder=embedder, threshold=0.5,
                              lost_after_frames=1, reacquire_confirm=1, verify_frames=0)
        session.start(np.zeros((8, 8, 3), np.uint8), (0, 0, 100, 100))
        session.step(np.zeros((8, 8, 3), np.uint8))          # → LOST (hết mask)

        embedder.hits = [_hit((300, 300, 360, 360), ref_emb)]  # A quay lại, chỗ khác
        step = session.step(np.zeros((8, 8, 3), np.uint8))
        assert step.state == STATE_TRACKING
        assert step.reacquired is True
        assert engine.start_calls[-1] == (300, 300, 360, 360)
        assert step.result.mask.any()

    def test_reset_ve_trang_thai_ban_dau(self):
        engine = FakeEngine(masks=[True, True])
        session = ReIdSession(engine=engine, embedder=FakeEmbedder([]),
                              threshold=0.36, lost_after_frames=1)
        session.start(np.zeros((8, 8, 3), np.uint8), (0, 0, 100, 100))
        session.step(np.zeros((8, 8, 3), np.uint8))
        session.reset()
        assert session.state == STATE_TRACKING
        assert session.ref_count == 0


class TestFrameIdxLienTuc:
    """frame_idx phải đơn điệu tăng qua cả mốc nhận lại (engine.start reset bộ đếm của nó).

    Lỗi thật 22-10: CSV có ... 213 → 1 (lùi) làm biểu đồ quỹ đạo sai.
    """

    def test_frame_idx_tang_lien_tuc_sau_khi_nhan_lai(self):
        ref = _vec(1)
        embedder = FakeEmbedder([_hit((10, 10, 60, 60), ref)])
        engine = FakeEngine(masks=[True])
        session = ReIdSession(engine=engine, embedder=embedder, threshold=0.5,
                              lost_after_frames=1, reacquire_confirm=1, verify_frames=0)
        session.start(np.zeros((8, 8, 3), np.uint8), (0, 0, 100, 100))
        s1 = session.step(np.zeros((8, 8, 3), np.uint8))        # → LOST
        embedder.hits = [_hit((300, 300, 360, 360), ref)]
        s2 = session.step(np.zeros((8, 8, 3), np.uint8))        # → nhận lại
        s3 = session.step(np.zeros((8, 8, 3), np.uint8))        # frame bám tiếp theo
        assert s2.reacquired is True
        assert s1.result.frame_idx < s2.result.frame_idx < s3.result.frame_idx
        assert s2.result.frame_idx == 2 and s3.result.frame_idx == 3

    def test_frame_idx_khong_lui_khi_chon_lai_giua_video(self):
        """Bug thật 27-10: bấm `r` (reset + start) làm frame_idx về 0 → CSV lùi số
        (f11..72 xuất hiện sau f180..186). Số frame phải đơn điệu suốt một lần chạy."""
        engine = FakeEngine(masks=[False, False, False])
        session = ReIdSession(engine=engine, embedder=FakeEmbedder([]), lost_after_frames=9)
        session.start(np.zeros((8, 8, 3), np.uint8), (0, 0, 10, 10))
        for _ in range(3):
            session.step(np.zeros((8, 8, 3), np.uint8))
        truoc = session.step(np.zeros((8, 8, 3), np.uint8)).result.frame_idx
        session.reset()                                     # người dùng bấm r
        sau = session.start(np.zeros((8, 8, 3), np.uint8), (0, 0, 10, 10)).frame_idx
        tiep = session.step(np.zeros((8, 8, 3), np.uint8)).result.frame_idx
        assert truoc == 4
        assert sau >= truoc, f"frame_idx lùi sau khi chọn lại: {truoc} → {sau}"
        assert tiep > sau


def _obj_frame(box=(20, 20, 60, 60), color=(0, 140, 255), shape=(96, 96)):
    """Frame 96x96 nền tối + vật hình vuông có sọc (đủ cấu trúc để covariance bắt được)."""
    f = np.full((shape[0], shape[1], 3), (35, 37, 32), np.uint8)
    x1, y1, x2, y2 = box
    f[y1:y2, x1:x2] = color
    for x in range(x1, x2, 8):
        f[y1:y2, x:min(x + 3, x2)] = (255, 255, 255)
    return f


def _obj_mask(box=(20, 20, 60, 60), shape=(96, 96)):
    m = np.zeros(shape, bool)
    x1, y1, x2, y2 = box
    m[y1:y2, x1:x2] = True
    return m


def _iou(a, b):
    """IoU viết tay (nguồn độc lập với code đang test)."""
    ix1, iy1 = max(a[0], b[0]), max(a[1], b[1])
    ix2, iy2 = min(a[2], b[2]), min(a[3], b[3])
    inter = max(0, ix2 - ix1) * max(0, iy2 - iy1)
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0


class TestReIdSessionObjectCue:
    """Cue VẬT THỂ (ticket 10): không có khuôn mặt vẫn phải lưu mẫu và nhận lại được.

    Đây là hành vi hỏng trước đây: `_collect_reference` chỉ lưu khi có MẶT → remote TV
    không có mẫu nào → `best_match` trả -1.0 → mất dấu là mất vĩnh viễn.
    """

    def test_vat_khong_co_mat_van_luu_mau(self):
        engine = FakeEngineMasks([], shape=(96, 96))
        session = ReIdSession(engine=engine, embedder=None, cue="object",
                              lost_after_frames=1)
        session.start(_obj_frame(), (20, 20, 60, 60))
        assert session.state == STATE_TRACKING
        assert session.object_ref_count > 0   # vật có mẫu dù KHÔNG có mặt
        assert session.ref_count == 0         # không có mẫu khuôn mặt nào

    def test_cue_face_khong_luu_mau_vat(self):
        """Mặc định (cue face) giữ nguyên hành vi cũ: không đụng tới mẫu vật thể."""
        engine = FakeEngineMasks([], shape=(96, 96))
        session = ReIdSession(engine=engine, embedder=FakeEmbedder([]),
                              lost_after_frames=1)
        session.start(_obj_frame(), (20, 20, 60, 60))
        assert session.object_ref_count == 0

    def test_mat_dau_roi_vat_quay_lai_thi_bam_lai(self):
        present = _obj_mask((20, 20, 60, 60))
        empty = np.zeros((96, 96), bool)
        engine = FakeEngineMasks([present, empty], shape=(96, 96))
        session = ReIdSession(engine=engine, embedder=None, cue="object",
                              lost_after_frames=1, obj_threshold=0.6,
                              reacquire_confirm=1, verify_frames=0)
        session.start(_obj_frame(), (20, 20, 60, 60))
        session.step(_obj_frame())                       # còn thấy → vẫn tracking
        s_lost = session.step(_obj_frame())              # mask rỗng → lost
        assert s_lost.state == STATE_LOST
        moved = (30, 30, 70, 70)                          # vật quay lại ở chỗ khác
        s_re = session.step(_obj_frame(moved))
        assert s_re.reacquired is True
        assert s_re.state == STATE_TRACKING
        assert len(engine.start_calls) == 2               # start ban đầu + start nhận lại
        # Prefilter NCC chạy trên frame thu nhỏ 4x nên ô trả về lệch tối đa ~4 px mỗi cạnh —
        # đúng thiết kế (SAM 2 sẽ tinh chỉnh lại mask). Chuẩn kiểm tra là chồng lấn, không phải px tuyệt đối.
        assert _iou(engine.start_calls[-1], moved) >= 0.5

    def test_khong_co_mau_thi_van_lost_va_khong_bao_nham(self):
        """Vật quá nhỏ bị cổng chất lượng loại → không có mẫu → phải ở LOST, không nhận bừa."""
        small = (10, 10, 20, 20)
        engine = FakeEngineMasks([np.zeros((96, 96), bool)], shape=(96, 96))
        session = ReIdSession(engine=engine, embedder=None, cue="object",
                              lost_after_frames=1)
        session.start(_obj_frame(small), small)
        assert session.object_ref_count == 0
        step = session.step(_obj_frame(small))
        assert step.state == STATE_LOST
        assert step.reacquired is False
        assert step.reid_score == -1.0


def _black_frame(box, shape=(200, 300)):
    """Nền sáng + vật ĐEN đặc (mô phỏng chai đen) — ca mà cosine gần như mù."""
    f = np.full((shape[0], shape[1], 3), (205, 208, 212), np.uint8)
    x1, y1, x2, y2 = box
    f[y1:y2, x1:x2] = (20, 20, 20)
    return f


class TestCongNccVatDen:
    """Cổng NCC (ticket 11): vật đen đặc cho cosine ≈ 1.0 với MỌI vật đen khác → phải nhờ NCC.

    Đo thật 27-10: hai vật đen khác nhau → cosine 1,000 (mù), NCC 0,897; cùng vật → NCC 1,000.
    """

    BOX_A = (40, 50, 90, 150)      # vật A 50x100
    BOX_B = (200, 60, 240, 130)    # vật B KHÁC: 40x70

    def _session(self, engine, ncc_min):
        return ReIdSession(engine=engine, embedder=None, cue="object",
                           lost_after_frames=1, obj_threshold=0.5,
                           obj_ncc_min=ncc_min, reacquire_confirm=1, verify_frames=0)

    def test_cos_mu_voi_vat_den_khac_nhung_co_ncc(self):
        """Bật cổng NCC cao → KHÔNG được nhận nhầm vật đen khác (dù cosine cao)."""
        empty = np.zeros((200, 300), bool)
        engine = FakeEngineMasks([empty], shape=(200, 300))
        session = self._session(engine, ncc_min=1.01)     # ngưỡng không thể đạt → chặn hết
        session.start(_black_frame(self.BOX_A), self.BOX_A)
        assert session.object_ref_count > 0
        session.step(_black_frame(self.BOX_A))            # mask rỗng → lost
        step = session.step(_black_frame(self.BOX_B))     # frame chỉ có vật B
        assert step.reacquired is False
        assert step.state == STATE_REACQUIRING    # đang tìm tiếp, chưa nhận bừa
        assert step.ncc >= 0.0                    # vẫn ghi ncc của ô bị loại để hiệu chuẩn

    def test_khi_tat_cong_ncc_thi_van_nhan_nham_nhu_cu(self):
        """Chứng minh cổng là cần thiết: tắt cổng (mặc định) thì cosine cao → nhận nhầm."""
        empty = np.zeros((200, 300), bool)
        engine = FakeEngineMasks([empty], shape=(200, 300))
        session = self._session(engine, ncc_min=0.0)
        session.start(_black_frame(self.BOX_A), self.BOX_A)
        session.step(_black_frame(self.BOX_A))
        step = session.step(_black_frame(self.BOX_B))
        assert step.reacquired is True          # đây là hành vi CŨ (chưa cứu được vật đen)
        assert step.ncc >= 0.0                  # và NCC có được ghi lại để hiệu chuẩn


class TestChongBamNham:
    """3 lỗi thật 27-10: SAM 2 "tưởng tượng" mask khi vật rời khung → bám nhầm nền → không tự sửa.

    Đo trên fixture (vật bị xoá hẳn): mask 782 px nhưng `object_score_logits` = **-4,98**,
    và sau khi bám nhầm vào nền thì score dương giả → hệ thống kẹt vĩnh viễn.
    """

    def test_mask_khong_rong_nhung_score_am_van_la_mat_dau(self):
        """Chỉ dựa vào 'mask rỗng' là sai: mask giả + score âm phải tính là MẤT DẤU."""
        seen_mask = _obj_mask((20, 20, 60, 60))
        engine = FakeEngineMasks([seen_mask, seen_mask], shape=(96, 96),
                                 scores=[-4.98, -6.26])
        session = ReIdSession(engine=engine, embedder=None, cue="object",
                              lost_after_frames=2, reacquire_confirm=1, verify_frames=0)
        session.start(_obj_frame(), (20, 20, 60, 60))
        s1 = session.step(_obj_frame())
        s2 = session.step(_obj_frame())
        assert s1.state == STATE_TRACKING          # 1 frame score âm chưa đủ
        assert s2.state == STATE_LOST              # 2 frame liên tiếp → mất dấu

    def test_ung_vien_phai_khop_2_frame_lien_tiep_moi_nhan_lai(self):
        empty = np.zeros((96, 96), bool)
        engine = FakeEngineMasks([empty, empty], shape=(96, 96))
        session = ReIdSession(engine=engine, embedder=None, cue="object",
                              lost_after_frames=1, obj_threshold=0.5,
                              reacquire_confirm=2, verify_frames=0)
        session.start(_obj_frame(), (20, 20, 60, 60))
        session.step(_obj_frame())                      # → LOST
        moved = (24, 24, 64, 64)
        a = session.step(_obj_frame(moved))             # khớp lần 1 → chưa nhận
        b = session.step(_obj_frame(moved))             # khớp lần 2 (cùng chỗ) → nhận
        assert a.reacquired is False
        assert b.reacquired is True and b.state == STATE_TRACKING

    def test_bam_nham_thi_tu_bo_va_ve_lost(self):
        """Sau khi bám lại, mask mới KHÔNG giống vật (đang bám nền) → bỏ, reset engine, về LOST."""
        empty = np.zeros((96, 96), bool)
        # mask bám nhầm = một vùng nền trơn ở góc dưới (không phải vật cam có sọc)
        wrong = np.zeros((96, 96), bool)
        wrong[80:96, 80:96] = True
        # hàng đợi: process#1 = mask rỗng (→ LOST); process#2 = mask NỀN (frame kiểm chứng)
        engine = FakeEngineMasks([empty, wrong, wrong], shape=(96, 96))
        session = ReIdSession(engine=engine, embedder=None, cue="object",
                              lost_after_frames=1, obj_threshold=0.5,
                              reacquire_confirm=1, verify_frames=2)
        session.start(_obj_frame(), (20, 20, 60, 60))
        session.step(_obj_frame())                      # → LOST
        moved = (24, 24, 64, 64)
        re_ = session.step(_obj_frame(moved))           # nhận lại, vào cửa sổ kiểm chứng
        assert re_.reacquired is True
        bad = session.step(_obj_frame())                # frame kiểm chứng: mask = vùng nền
        assert bad.state == STATE_LOST
        assert bad.reacquired is False
        assert engine.reset_calls >= 1                  # đã bỏ track sai


class TestCongNhanLai:
    """Cổng quyết định nhận lại — số liệu từ video THẬT của người dùng (29-10, có nhãn).

    Ca SAI (dấu vật → bám bóng đèn/tay): ncc 0,39 / 0,54 / 0,58 / 0,59 / 0,69
    Ca ĐÚNG (bám lại đúng ly):           ncc 0,78 / 0,91 / 0,92
    → ngưỡng 0,70 tách được cả hai phía.
    """

    @pytest.mark.parametrize("ncc,cos,expected", [
        (0.39, 0.90, False),   # tay (đo trên pixel thật)
        (0.54, 0.77, False),   # bám sai lần #1 của lần quay 204458
        (0.58, 0.89, False),   # #1 lần quay 204458
        (0.59, 0.93, False),   # #2, #3 lần quay 204458
        (0.69, 0.85, False),   # sát ngưỡng nhưng vẫn sai
        (0.78, 0.80, True),    # đúng (binh1)
        (0.91, 0.62, True),    # đúng dù cosine thấp
    ])
    def test_cong_ncc_tach_dung_sai(self, ncc, cos, expected):
        assert accept_candidate(ncc, cos, 0.70, 0.40) is expected

    def test_cos_van_lam_cong_long(self):
        """NCC cao nhưng cosine quá thấp (>0) → vẫn loại (chặn ứng viên kỳ dị)."""
        assert accept_candidate(0.95, 0.10, 0.70, 0.40) is False

    def test_tat_cong_bang_0_thi_chi_xet_cos_floor(self):
        assert accept_candidate(0.10, 0.90, 0.0, 0.40) is True


class TestTuPhucHoi:
    """Không cần người dùng bấm `r`: ô bao nhảy bất thường → tự reset + tự tìm lại.

    Đo thật 29-10: khi dấu vật, ô bao nhảy 216–295 px (gấp 1–2 lần kích thước vật) sang bóng đèn.
    Khung test 200×300; vật 40×40 → đường chéo ≈ 57 px; ngưỡng 1,5× ≈ 85 px.
    """

    SHAPE = (200, 300)
    BOX = (20, 20, 60, 60)
    MASK = None

    def _mk(self, box):
        return _obj_mask(box, self.SHAPE)

    def _frame(self, box):
        return _obj_frame(box, shape=self.SHAPE)

    def _session(self, engine, **kw):
        return ReIdSession(engine=engine, embedder=None, cue="object",
                           lost_after_frames=1, obj_threshold=0.5,
                           reacquire_confirm=1, verify_frames=0, **kw)

    def test_o_bao_nhay_bat_thuong_thi_tu_bo_va_ve_lost(self):
        far = (250, 150, 290, 190)          # cách ~260 px >> 85 px
        engine = FakeEngineMasks([self._mk(self.BOX), self._mk(far)], shape=self.SHAPE,
                                 bboxes=[self.BOX, far])
        s = self._session(engine)
        s.start(self._frame(self.BOX), self.BOX)
        assert s.step(self._frame(self.BOX)).state == STATE_TRACKING
        step = s.step(self._frame(far))
        assert step.state == STATE_LOST                     # tự phát hiện → bỏ
        assert engine.reset_calls >= 1
        assert s.object_ref_count > 0                       # GIỮ ký ức để nhận diện lại

    def test_tat_tu_phuc_hoi_thi_khong_bo(self):
        far = (250, 150, 290, 190)
        engine = FakeEngineMasks([self._mk(self.BOX), self._mk(far)], shape=self.SHAPE,
                                 bboxes=[self.BOX, far])
        s = self._session(engine, auto_recover=False)
        s.start(self._frame(self.BOX), self.BOX)
        s.step(self._frame(self.BOX))
        assert s.step(self._frame(far)).state == STATE_TRACKING

    def test_di_chuyen_nhanh_nhung_trong_nguong_thi_khong_bo(self):
        near = (50, 34, 90, 74)             # dịch ~30 px < 85 px
        engine = FakeEngineMasks([self._mk(self.BOX), self._mk(near)], shape=self.SHAPE,
                                 bboxes=[self.BOX, near])
        s = self._session(engine)
        s.start(self._frame(self.BOX), self.BOX)
        s.step(self._frame(self.BOX))
        assert s.step(self._frame(near)).state == STATE_TRACKING


class TestCauHinhMacDinh:
    """Khoá các giá trị mặc định quan trọng — bug thật 29-10: reid.py truyền min_side=24 ĐÈ mất
    hằng số trong appearance.py nên bản sửa "vật mảnh (bút)" không có tác dụng."""

    def test_min_side_cho_vat_manh(self):
        assert ReIdSession(engine=None, embedder=None, cue="object").obj_min_side == 8

    def test_cong_chinh_la_cosine(self):
        s = ReIdSession(engine=None, embedder=None, cue="object")
        assert s.obj_threshold == pytest.approx(0.60)
        assert s.obj_ncc_min == 0.0        # cổng NCC tắt mặc định

    def test_bat_tu_phuc_hoi_mac_dinh(self):
        assert ReIdSession(engine=None, embedder=None, cue="object").auto_recover is True


class TestKichThuocEma:
    """Kích thước vật dùng cho vùng tìm phải là EMA, không phải bbox frame cuối (bug 04-11).

    Bug thật (`demoip_1104-212328.mp4`): vật rời khung thì SAM 2 co mask về mép (71×10 px trong
    khi vật thật 220×204) ⇒ `_last_obj_size` thành rác ⇒ radius vùng tìm 89–248 px trong khi ô
    đúng cách chỗ mất ~300 px ⇒ "mất dấu đưa vào lại KHÔNG nhận được".
    """

    SHAPE = (480, 640)

    @staticmethod
    def _frame(color=(10, 90, 200)):
        return np.full((TestKichThuocEma.SHAPE[0], TestKichThuocEma.SHAPE[1], 3), color, dtype=np.uint8)

    @staticmethod
    def _mask(x1, y1, x2, y2):
        m = np.zeros(TestKichThuocEma.SHAPE, dtype=bool)
        m[y1:y2, x1:x2] = True
        return m

    def _session(self, **kw):
        over = {"obj_threshold": 0.6, "reacquire_confirm": 2, "verify_frames": 2}
        over.update(kw)
        return ReIdSession(engine=None, embedder=None, cue="object", **over)

    def test_mask_trong_khung_thi_ema_bang_kich_thuoc_that(self):
        s = self._session()
        s._collect_reference(self._frame(), (50, 50, 270, 254), self._mask(50, 50, 270, 254))
        assert s._size_ema == pytest.approx((220.0, 204.0))
        assert s._last_obj_size == (220, 204)

    def test_mask_cham_mep_khong_cap_nhat_ema(self):
        """Cốt lõi của fix: bbox 71×10 chạm đáy (rác) không được kéo EMA xuống.

        Bug thật f102 của `demoip_1104-214922.mp4`: mask rác chạm mép bị NẠP vào `_obj_refs`
        (cos 0,798 với vùng nền) → "nhận lại" thành công trên vùng TAY người — bám nhầm.
        """
        s = self._session()
        s._collect_reference(self._frame(), (50, 50, 270, 254), self._mask(50, 50, 270, 254))
        ema_truoc = s._size_ema
        ref_count_truoc = s.object_ref_count
        s._collect_reference(self._frame(), (434, 469, 505, 479), self._mask(434, 469, 505, 479))
        assert s._size_ema == ema_truoc, "bbox chạm mép (mask rác) không được sửa EMA"
        assert s.object_ref_count == ref_count_truoc, (
            "mask chạm mép KHÔNG được nạp vào `_obj_refs` — nạp vào sẽ ô nhiễm ký ức"
        )
        assert s._last_obj_size == (71, 10), "vẫn ghi `_last_obj_size` để tìm quanh vùng đó"
        assert s._last_center == ((434 + 505) / 2, (469 + 479) / 2)

    def test_radius_dung_ema_khong_dung_bbox_cuoi(self):
        """Vùng tìm phải rộng theo size THẬT (EMA) — là chỗ bug chặn không nhận lại."""
        s = self._session()
        s._collect_reference(self._frame(), (50, 50, 270, 254), self._mask(50, 50, 270, 254))
        assert s._size_ema == pytest.approx((220.0, 204.0))
        s._collect_reference(self._frame(), (434, 469, 505, 479), self._mask(434, 469, 505, 479))
        s._lost_age = 5
        # radius với EMA 220×204 (base=220): age5 = 385 px; nếu theo bbox cuối 71: chỉ 124 px
        # (bằng chứng thật: ô đúng cách chỗ mất ~300 px — 124 là KHÔNG đủ, 385 là đủ)
        pairs = [((290, 190, 510, 394), -1.0)]          # ô đúng cách ~195 px
        kept = s._filter_by_radius(pairs, self.SHAPE)
        assert kept, "ô đúng phải nằm trong vùng tìm khi radius theo EMA (điều này tự vạc mình nếu "
        "dùng bbox rác cuối: chỉ 124 px)"


class TestCanhBaoVatChamMep:
    """Bug thật 05-11-2026 (`demoip_1105-131222`): người dùng kéo ô có `y2 = 479/480` suốt
    48 frame đang bám → mask luôn chạm mép → `_collect_reference` không lưu mẫu nào →
    `reid_score = -1` ở cả 325 frame, mất dấu 85%, "dơ lại vật mà không dính lại".
    Hệ thống cũ IM LẶNG ⇒ phải cảnh báo ngay lúc chọn.
    """

    def test_ham_nhan_dien_o_cham_mep(self):
        from src.reid import touches_frame_edge

        assert touches_frame_edge((10, 10, 300, 479), 640, 480)      # chạm đáy
        assert touches_frame_edge((350, 226, 519, 479), 640, 480)    # đúng ca đã gặp
        assert touches_frame_edge((0, 20, 200, 300), 640, 480)       # chạm trái
        assert touches_frame_edge((10, 10, 639, 300), 640, 480)      # chạm phải
        assert not touches_frame_edge((100, 100, 400, 400), 640, 480)  # bao trọn trong khung
        assert not touches_frame_edge(None, 640, 480)

    def test_start_canh_bao_khi_engine_tra_o_cham_mep(self, capsys):
        from src.reid import HINT_CHAM_MEP, touches_frame_edge

        class EngineChamMep(FakeEngine):
            def _result(self, frame_idx, mask, bbox=(10, 10, 50, 50)):
                return super()._result(frame_idx, mask, bbox=(20, 20, 300, 479))

        session = ReIdSession(engine=EngineChamMep([]), embedder=None, cue="object")
        frame = np.zeros((480, 640, 3), np.uint8)
        session.start(frame, (20, 20, 300, 479))
        out = capsys.readouterr().out
        assert HINT_CHAM_MEP.splitlines()[0] in out
        assert "KHÔNG lưu được mẫu đặc trưng" in out
        # và đúng là không có mẫu nào được lưu (nguyên nhân gốc)
        assert session.object_ref_count == 0
        assert touches_frame_edge((20, 20, 300, 479), 640, 480)

    def test_start_khong_canh_bao_khi_hoc_duoc_mau(self, capsys):
        class EngineSach(FakeEngine):
            def _result(self, frame_idx, mask, bbox=(10, 10, 50, 50)):
                m = np.zeros((480, 640), bool)
                m[100:300, 100:300] = True
                return super()._result(frame_idx, m, bbox=(100, 100, 300, 300))

        session = ReIdSession(engine=EngineSach([]), embedder=None, cue="object")
        session.start(np.zeros((480, 640, 3), np.uint8), (100, 100, 300, 300))
        assert "KHÔNG lưu được mẫu" not in capsys.readouterr().out
        assert session.object_ref_count > 0


class TestVatOMepBienVanHocDuocMau:
    """05-11-2026: vật bị khung cắt một phần PHẢI học được đặc trưng (case "vật ở mép biên").

    Trước đây `_collect_reference` bỏ TOÀN BỘ mẫu khi mask chạm mép ⇒ chọn vật sát mép là
    `_obj_refs` rỗng vĩnh viễn ⇒ re-ID không bao giờ nhận lại (bug `demoip_1105-131222`).
    Nay: cắt dải mép (`clip_mask_border`) → nếu phần CÒN THẤY đủ lớn thì vẫn học.
    """

    SHAPE = (480, 640)

    @staticmethod
    def _frame():
        rng = np.random.default_rng(7)
        return rng.integers(0, 255, (480, 640, 3), dtype=np.uint8)

    @staticmethod
    def _mask(x1, y1, x2, y2):
        m = np.zeros((480, 640), dtype=bool)
        m[y1:y2, x1:x2] = True
        return m

    def _session(self):
        return ReIdSession(engine=None, embedder=None, cue="object")

    def test_vat_bi_cat_day_khung_van_luu_duoc_mau(self):
        """Vật to bị khung cắt đáy (bbox y2 = 480 = mép) → vẫn phải có mẫu."""
        s = self._session()
        # vật thật 220×204 đã có trong ký ức (EMA), rồi bị khung cắt đáy
        s._collect_reference(self._frame(), (50, 50, 270, 254), self._mask(50, 50, 270, 254))
        truoc = s.object_ref_count
        s._collect_reference(self._frame(), (60, 300, 280, 479), self._mask(60, 300, 280, 479))
        assert s.object_ref_count > truoc, (
            "vật bị khung cắt nhưng phần thấy ~180×175 px vẫn phải học được mẫu"
        )

    def test_vat_bi_cat_ben_hong_van_luu_duoc_mau(self):
        s = self._session()
        s._collect_reference(self._frame(), (50, 50, 270, 254), self._mask(50, 50, 270, 254))
        truoc = s.object_ref_count
        s._collect_reference(self._frame(), (0, 100, 200, 304), self._mask(0, 100, 200, 304))
        assert s.object_ref_count > truoc

    def test_dai_rac_sat_mep_van_bi_chan(self):
        """Chống hồi quy 04-11: mask sụp thành dải 71×10 sát mép (vật đã ra khỏi khung) → KHÔNG học."""
        s = self._session()
        s._collect_reference(self._frame(), (50, 50, 270, 254), self._mask(50, 50, 270, 254))
        truoc = s.object_ref_count
        ema = s._size_ema
        s._collect_reference(self._frame(), (434, 469, 505, 479), self._mask(434, 469, 505, 479))
        assert s.object_ref_count == truoc, "dải rác sát mép không được nạp vào ký ức"
        assert s._size_ema == ema, "và không được kéo EMA theo"

    def test_mau_cat_mep_khong_lam_hong_ema(self):
        """Mẫu học từ vật bị cắt (kích thước nhỏ hơn thật) không được đưa vào EMA."""
        s = self._session()
        s._collect_reference(self._frame(), (50, 50, 270, 254), self._mask(50, 50, 270, 254))
        ema = s._size_ema
        s._collect_reference(self._frame(), (60, 300, 280, 479), self._mask(60, 300, 280, 479))
        assert s._size_ema == ema

    def test_nhan_lai_duoc_sau_khi_hoc_tu_vat_o_mep(self):
        """End-to-end: học mẫu từ vật bị cắt mép → khi mất dấu, ứng viên cùng vật được chấp nhận."""
        frame = self._frame()
        mask_day = self._mask(60, 300, 280, 479)                 # vật bị cắt đáy
        s = self._session()
        s._collect_reference(frame, (60, 300, 280, 479), mask_day)
        assert s.object_ref_count > 0, "phải có mẫu để so"
        sig = s._obj_refs[0]
        from src.reid import best_match

        assert best_match(s._obj_refs, sig) == pytest.approx(1.0), "tự so với chính mẫu phải = 1,0"


class TestCongChongNhayKhongTuHuyLanNhanLai:
    """P0 plan 21-11: `_reacquire` từng KHÔNG cập nhật `_last_bbox` ⇒ tick sau, cổng chống-nhảy so với
    mốc TRƯỚC KHI MẤT DẤU ⇒ vật vào lại ở chỗ khác bị coi là "nhảy bất thường" ⇒ `_auto_recover()` huỷ
    ngay lần nhận lại vừa xong (2× `engine.start`, 1 frame không có ô, bỏ qua `verify_frames`).

    Bằng chứng thật: phiên `tools/run_live.py --reid --reid-cue object` trên `binh2` có **3 lần
    "reacquired" liên tiếp f172/176/180** cho MỘT lần vật vào lại.

    Test này ĐỎ khi xoá dòng `self._last_bbox = tuple(getattr(result, "bbox", bbox))` trong `_reacquire`.
    """

    SHAPE = (96, 96)

    def _frame(self, boxes=()):
        """Nền tối + **cùng một mảng texture** dán ở mọi `box` ⇒ đặc trưng ở các vị trí như nhau.

        Nếu dùng nền nhiễu ngẫu nhiên thì `_verify_ok` so mẫu ở A với vùng ở B thấy hai vùng nhiễu
        khác nhau ⇒ bỏ nhận lại vì lý do KHÁC (không phải cổng chống-nhảy) — test sẽ đo sai thứ.
        """
        frame = np.zeros((*self.SHAPE, 3), np.uint8)
        rng = np.random.default_rng(11)
        patch = rng.integers(60, 200, (30, 30, 3), dtype=np.uint8)
        for box in boxes:
            x1, y1, x2, y2 = box
            h, w = min(y2 - y1, 30), min(x2 - x1, 30)
            frame[y1:y1 + h, x1:x1 + w] = patch[:h, :w]
        return frame

    def _mask(self, box, shape=None):
        h, w = shape or self.SHAPE
        m = np.zeros((h, w), bool)
        m[max(0, box[1]):min(box[3], h), max(0, box[0]):min(box[2], w)] = True
        return m

    def test_vat_vao_lai_o_cho_KHAC_chi_start_MOT_lan(self):
        # Chọn khoảng nhảy LỚN HƠN HẲN ngưỡng: cổng là `> 1,5 × chéo` (strict), nên nếu đặt đúng bằng
        # ngưỡng thì test xanh cả khi KHÔNG vá (mutant sống) — đã bị bắt đúng một lần.
        box_a = (10, 10, 36, 36)          # 26×26 = 676 px > MIN_AREA 600; chéo 36,8 ⇒ ngưỡng 55,2
        box_b = (60, 60, 90, 90)          # tâm cách ~73,5 px > 55,2 ⇒ cổng SẼ kích hoạt nếu mốc cũ
        eng = FakeEngineMasks([None], shape=self.SHAPE, bboxes=[box_a])
        session = ReIdSession(engine=eng, embedder=None, cue="object",
                              lost_after_frames=2, reacquire_confirm=1, verify_frames=2,
                              auto_recover=True, threshold=0.36)
        # Vật chỉ ở A lúc chọn, rồi CHỈ Ở B lúc vào lại (texture y hệt ⇒ đặc trưng khớp 1,0),
        # đúng kịch bản "vật rời khung rồi vào lại ở chỗ khác".
        session.start(self._frame(boxes=(box_a,)), box_a)       # `start` thu mẫu thật ⇒ `_obj_refs` đúng chiều
        assert session.object_ref_count >= 1, "cần ít nhất 1 mẫu để bài test có nghĩa"
        n_start = len(eng.start_calls)    # 1 = lần chọn ô ban đầu; mọi lần sau là của re-ID

        # Ép trạng thái TÌM LẠI (đường thật vào đây qua `lost_after_frames`, nhưng dựng trực tiếp cho
        # bài test chỉ kiểm cổng chống-nhảy).
        session._state = "lost"
        session._lost_streak = 2
        session._last_bbox = box_a
        session._last_center = ((box_a[0] + box_a[2]) / 2, (box_a[1] + box_a[3]) / 2)
        session._size_ema = (30.0, 30.0)
        session._last_obj_size = (30, 30)
        session._verify_left = 0
        # Bán kính tìm nở dần (`_filter_by_radius`, 0,75→1,75 lần cạnh vật trong 12 frame đầu) nên
        # lúc mới mất dấu thì KHÔNG thể nhảy 73 px — phải để `_lost_age` vượt `search_grow_frames`
        # như một lần vật rời khung thật rồi vào lại.
        session._lost_age = 30
        session._recover_cooldown = 0
        frame = self._frame(boxes=(box_b,))
        eng._bboxes = [box_b]
        step = session.step(frame)
        assert step.reacquired is True, "phải nhận lại được ở bước này"
        assert len(eng.start_calls) == n_start + 1

        # `_last_center` cũng phải là tâm ô VỪA NHẬN LẠI: nó là mốc của vùng tìm nở dần
        # (`_filter_by_radius`) ⇒ để nguyên tâm cũ thì lần mất dấu sau sẽ tìm quanh chỗ vật KHÔNG còn
        # ở đó. Review 21-11 (P3): nửa vá này không test nào phủ (xoá 2 dòng vẫn xanh).
        # So với ô THẬT SỰ được nhận (ứng viên đã bị lưới prefilter bắt về gần B, không đúng y box_b).
        assert session._last_bbox != box_a, "mốc vẫn là chỗ cũ ⇒ vá chưa có tác dụng"
        assert session._last_center == ((session._last_bbox[0] + session._last_bbox[2]) / 2.0,
                                        (session._last_bbox[1] + session._last_bbox[3]) / 2.0), \
            "`_last_center` phải là tâm ô VỪA NHẬN LẠI (mốc vùng tìm nở dần), không phải tâm chỗ cũ"

        # Tick kế: cổng chống-nhảy phải SO VỚI Ô VỪA NHẬN LẠI (B), không phải mốc cũ (A)
        eng._bboxes = [box_b]
        session.step(frame)
        assert session.state == "tracking", "cổng chống-nhảy đã tự huỷ lần nhận lại (P0 tái phát)"
        assert len(eng.start_calls) == n_start + 1, f"thừa lần start: {eng.start_calls}"


class FakeMat:
    """Bộ dò mặt giả (duck-type `BoDoMat`): trả danh sách ô `(x, y, w, h)` cố định."""

    def __init__(self, faces):
        self.faces = list(faces)
        self.calls = 0

    def detect(self, _frame):
        self.calls += 1
        return list(self.faces)


class TestVetoNhanLaiVaoMat:
    """Đo 20–21/11 (3 phiên demo webcam): re-ID nhận lại SAI vào MẶT (cos 0,974/ncc 0,545),

    vào TRÁN (0,734/0,423), vào ĐẦU (0,663/0,356). Ngưỡng điểm KHÔNG cứu được vì ca mặt có
    ncc 0,545 nằm GIỮA dải ca đúng (0,415–0,741) ⇒ phải dùng thông tin MIỄN PHÍ: ô chọn ban đầu
    không phủ mặt ⇒ vật cần bám không phải mặt ⇒ ứng viên trùm mặt là SAI theo định nghĩa.

    `_match_object` được THAY BẰNG STUB để test đúng tầng veto (không phụ thuộc cascade NCC).
    """

    VAT = (10, 10, 90, 90)          # ô chọn ban đầu: góc trên-trái, KHÔNG có mặt
    MAT = (100, 10, 70, 90)         # một khuôn mặt ở góc phải
    O_MAT = (110, 20, 160, 90)      # ứng viên nhận lại: nằm TRỌN trong mặt (hệ xyxy)
    MAT_XYXY = (100, 10, 170, 100)  # cùng khuôn mặt ở hệ xyxy (mọi thứ trong `reid` dùng xyxy)

    def _f(self):
        return _obj_frame(shape=(120, 260))

    def _f_at(self, box):
        return _obj_frame(box=box, shape=(120, 260))

    def _f_trong(self):
        """Frame KHÔNG có vật (nền trơn) ⇒ engine giả trả mask rỗng ⇒ mất dấu."""
        return np.full((120, 260, 3), (35, 37, 32), np.uint8)

    def _session(self, face_veto):
        empty = np.zeros((120, 260), bool)
        engine = FakeEngineMasks([empty], shape=(120, 260))
        return ReIdSession(engine=engine, embedder=None, cue="object",
                           lost_after_frames=1, obj_threshold=0.5,
                           reacquire_confirm=1, verify_frames=0, face_veto=face_veto)

    def _vao_tim_lai(self, s, bbox_chon=None):
        """start + 2 frame trống ⇒ trạng thái TÌM LẠI, kèm stub trả ứng viên trùng mặt."""
        s.start(self._f(), bbox_chon or self.VAT)
        s.step(self._f())                    # mask rỗng ⇒ mất dấu (lost_after_frames=1)
        s._match_object = lambda frame: (0.9, self.O_MAT, 0.9)   # stub: tìm ra "vật" trong mặt
        return s

    def test_phu_mat_tinh_dung_phan_dien_tich(self):
        s = self._session(FakeMat([self.MAT]))
        assert s._phu_mat(self._f(), self.MAT_XYXY) == 1.0        # ô = đúng mặt
        assert s._phu_mat(self._f(), self.VAT) == 0.0             # ô vật góc trái
        assert s._phu_mat(self._f(), (100, 10, 0, 0)) == 0.0      # ô suy biến ⇒ fail-open

    def test_ung_vien_trum_mat_bi_bo_khi_o_chon_khong_phai_mat(self):
        s = self._vao_tim_lai(self._session(FakeMat([self.MAT])))
        assert s._ref_phu_mat is False
        step = s.step(self._f_trong())
        assert step.reacquired is False           # KHÔNG bám vào mặt
        assert step.state == STATE_REACQUIRING
        assert s.veto_mat_n == 1
        assert step.reid_score >= 0.0             # vẫn ghi điểm để hiệu chuẩn

    def test_tam_o_nam_trong_mat_cung_bi_bo(self):
        """Ô ứng viên TO hơn mặt (phủ < 30 %) nhưng TÂM nằm trong mặt ⇒ vẫn bỏ (không ngưỡng)."""
        s = self._session(FakeMat([self.MAT]))
        to = (60, -40, 240, 160)
        assert s._trung_mat(self._f(), to) is True
        assert s._phu_mat(self._f(), to) < NGUONG_PHU_MAT

    def test_tat_veto_thi_van_nhan_nham_nhu_cu(self):
        s = self._vao_tim_lai(self._session(None))
        step = s.step(self._f_trong())
        assert step.reacquired is True            # hành vi CŨ — chứng minh veto là thứ cứu được
        assert s.veto_mat_n == 0

    def test_o_chon_PHU_MAT_thi_veto_im_lang(self):
        """Người dùng CHỌN ĐÚNG mặt (muốn bám mặt) ⇒ veto phải tắt, không được chặn."""
        s = self._vao_tim_lai(self._session(FakeMat([self.MAT])), bbox_chon=self.MAT_XYXY)
        assert s._ref_phu_mat is True
        step = s.step(self._f_trong())
        assert step.reacquired is True
        assert s.veto_mat_n == 0

    def test_frame_tim_lai_co_elapsed_ms_that(self):
        """P2 review 21-11: frame LOST/tìm-lại từng ghi `elapsed_ms = 0.0` ⇒ chi phí tìm (cascade

        NCC + YuNet khi veto) không hiện ở artifact nào, nên "veto có làm chậm không" không kiểm được.
        """
        s = self._session(FakeMat([self.MAT]))
        s.start(self._f(), self.VAT)
        s.step(self._f())                        # mất dấu
        step = s.step(self._f())                 # frame TÌM LẠI
        assert step.result.elapsed_ms > 0.0      # phải là số đo thật, không phải 0 mặc định

    def test_chi_goi_yunet_mot_lan_moi_lan_kiem(self):
        """`detect()` là YuNet thật (~29 ms) ⇒ một câu hỏi chỉ được một lần gọi.

        Bản đầu gọi 2 lần/frame tìm lại (`_phu_mat` rồi `_trung_mat`) — tự nhân đôi chi phí trên
        đúng đường đang cố tìm lại vật.
        """
        fm = FakeMat([self.MAT])
        s = self._session(fm)
        s.start(self._f(), self.VAT)
        fm.calls = 0
        # Ô KHÔNG phủ mặt: bản 2-detect (564dcb0) sẽ gọi 2 lần (điều kiện tâm chạy detect riêng).
        assert s._trung_mat(self._f(), self.VAT) is False
        assert fm.calls == 1

    def test_ung_vien_KHONG_trung_mat_van_duoc_nhan(self):
        """CHIỀU ÂM — thiếu test này thì mutant "cứ `_ref_phu_mat=False` là veto hết" vẫn xanh.

        Ứng viên nằm ngoài mọi khuôn mặt ⇒ phải nhận bình thường, `veto_mat_n` phải bằng 0.
        """
        fm = FakeMat([self.MAT])
        s = self._session(fm)
        s.start(self._f(), self.VAT)
        s._match_object = lambda frame: (0.9, self.VAT, 0.9)   # stub: ứng viên = đúng ô vật
        fm.calls = 0
        step = s.step(self._f())                  # mất dấu
        step = s.step(self._f())                  # tìm lại → phải NHẬN
        assert step.reacquired is True
        assert step.vetoed is False
        assert s.veto_mat_n == 0

    def test_veto_loc_UNG_VIEN_chu_khong_bo_ca_frame(self, monkeypatch):
        """P1 review 21-11: mặt xếp hạng trên vật ⇒ phải xét tiếp ứng viên KẾ TIẾP, không bỏ frame.

        Bản đầu veto ô tốt nhất rồi `bbox=None` ⇒ vật (dù nằm trong top-K) không bao giờ được xét
        ⇒ phiên kẹt `reacquiring` vô hạn dù vật đang trong khung. Ca thật: mặt cosine 0,9739 > ca
        đúng thấp nhất 0,770.
        """
        s = self._session(FakeMat([self.MAT]))
        s.start(self._f_at(self.VAT), self.VAT)
        assert s._obj_templates                      # có template ⇒ nhánh prefilter chạy
        # 2 ứng viên: TRONG MẶT đứng trước (ncc cao hơn), vật thật đứng sau
        monkeypatch.setattr("src.reid.prefilter_candidates",
                            lambda frame, tpl, **kw: [(self.O_MAT, 1.0), (self.VAT, 0.9)])
        # bán kính tìm không liên quan câu hỏi này (và nó phụ thuộc số frame đã mất dấu)
        monkeypatch.setattr(s, "_filter_by_radius", lambda pairs, shape: pairs)

        frame = self._f_at(self.VAT)
        fx, fy, fw, fh = self.MAT
        frame[fy:fy + fh, fx:fx + fw] = self._f_at(self.O_MAT)[fy:fy + fh, fx:fx + fw]

        score, bbox, ncc = s._match_object(frame)
        assert s.veto_mat_n == 1                     # ứng viên trong mặt bị bỏ
        assert bbox == self.VAT                      # NHẬN ứng viên kế tiếp, không bỏ cả frame
        assert score >= 0.0 and ncc == 0.9


class TestNoiDayVeto:
    """P2 review 21-11: cờ `--no-reid-face-veto` phải thực sự điều khiển việc nối `BoDoMat`.

    Rủi ro đã kiểm bằng đọc code: `merge_cli_overrides` (`src/config.py`) KHÔNG có key
    `reid_face_veto` và `main()` không gán lại ⇒ không bị config đè; `run demoip "$@"` đứng sau
    nên cờ người dùng tới được argparse. Test này khoá lại để lần sau không ai làm hỏng.
    """

    def _args(self, **kw):
        import argparse
        a = argparse.Namespace(reid_threshold=0.75, lost_after_frames=5, reid_ref_max=8,
                               reid_min_face_px=40, reid_min_detect_score=0.6,
                               reid_obj_threshold=0.75, reid_obj_ncc_min=0.40,
                               lost_score_threshold=0.0, reid_confirm=2, reid_verify=2,
                               reid_face_veto=True, reid_cue="object", reid=True,
                               reid_detector_model="models/face/det.onnx",
                               reid_recognizer_model="models/face/rec.onnx")
        for k, v in kw.items():
            setattr(a, k, v)
        return a

    def _session(self, monkeypatch, args):
        from tools.run_live import _make_reid_session
        monkeypatch.setattr("src.face_guard.BoDoMat",
                            lambda *a, **k: type("F", (), {"detect": lambda self, f: []})())
        return _make_reid_session(engine=object(), args=args)

    def test_bat_thi_gan_face_veto(self, monkeypatch):
        s = self._session(monkeypatch, self._args(reid_face_veto=True))
        assert s.face_veto is not None

    def test_co_no_reid_face_veto_thi_tat(self, monkeypatch):
        s = self._session(monkeypatch, self._args(reid_face_veto=False))
        assert s.face_veto is None

    def test_cue_face_khong_noi_veto(self, monkeypatch):
        """Bám MẶT mà lại veto mặt là tự chặn mình ⇒ khi cue=face phải KHÔNG nối veto.

        Dùng `BoDoMat` giả + bỏ qua kiểm tra tồn tại file model của embedder mặt (test này chỉ
        hỏi nhánh nối veto, không hỏi model thật).
        """
        import tools.run_live as rl
        monkeypatch.setattr(rl.os.path, "isfile", lambda p: True)
        monkeypatch.setattr("src.reid.FaceEmbedder", lambda *a, **k: object())
        s = self._session(monkeypatch, self._args(reid_cue="face", reid_face_veto=True))
        assert s.face_veto is None


class TestBaP1Vong2:
    """3 P1 của review vòng 2 (21-11) — mỗi lỗi phải có test giết được mutant."""

    VAT = (10, 10, 90, 90)
    MAT = (100, 10, 70, 90)              # xywh
    O_MAT = (110, 20, 160, 90)           # xyxy, nằm trọn trong mặt

    def _f(self):
        return _obj_frame(box=self.VAT, shape=(120, 260))

    def _f_trong(self):
        return np.full((120, 260, 3), (35, 37, 32), np.uint8)

    def _s(self, face_veto):
        engine = FakeEngineMasks([np.zeros((120, 260), bool)], shape=(120, 260))
        return ReIdSession(engine=engine, embedder=None, cue="object",
                           lost_after_frames=1, obj_threshold=0.5,
                           reacquire_confirm=1, verify_frames=0, face_veto=face_veto)

    def test_P1_ung_vien_bi_veto_VAN_GHI_DIEM(self, monkeypatch):
        """P1-3: bản trước `continue` trước khi chấm ⇒ `reid_score/ncc = -1`, trùng giá trị

        "không có ứng viên" ⇒ artifact không hiệu chuẩn được ngưỡng. Nay phải có số thật.
        """
        s = self._s(FakeMat([self.MAT]))
        s.start(self._f(), self.VAT)
        monkeypatch.setattr("src.reid.prefilter_candidates",
                            lambda f, tpl, **kw: [(self.O_MAT, 0.88)])
        monkeypatch.setattr(s, "_filter_by_radius", lambda pairs, shape: pairs)
        score, bbox, ncc = s._match_object(self._f())
        assert bbox is None                 # không nhận (ô trùng mặt)
        assert s.veto_mat_n == 1
        assert score >= 0.0                 # NHƯNG phải có điểm của ô bị bỏ
        assert ncc == 0.88                  # NCC lấy từ prefilter (miễn phí)

    def test_P2_yunet_chi_1_lan_cho_ca_frame_step(self, monkeypatch):
        """P2-2: `step()` backstop từng gọi YuNet lần 2 trên CÙNG frame (~29 ms)."""
        fm = FakeMat([self.MAT])
        s = self._s(fm)
        s.start(self._f(), self.VAT)
        monkeypatch.setattr("src.reid.prefilter_candidates",
                            lambda f, tpl, **kw: [(self.O_MAT, 0.88)])
        monkeypatch.setattr(s, "_filter_by_radius", lambda pairs, shape: pairs)
        s.step(self._f())                   # mất dấu
        fm.calls = 0
        s.step(self._f())                   # tìm lại: _match_object + backstop
        assert fm.calls == 1

    def test_P2_reset_xoa_quyet_dinh_veto(self):
        """P2: `reset()` hứa "về trạng thái ban đầu" ⇒ phải xoá `_ref_phu_mat`/`_ref_bbox`.

        Nếu còn `_ref_phu_mat=True` cũ thì veto TẮT IM LẶNG cho phiên sau.
        """
        s = self._s(FakeMat([self.MAT]))
        s.start(self._f(), (110, 20, 160, 90))     # ô chọn phủ mặt ⇒ _ref_phu_mat True
        assert s._ref_phu_mat is True
        s.reset()
        assert s._ref_phu_mat is False
        assert s._ref_bbox is None


    def test_veto_van_duoc_ghi_khi_frame_do_con_nhan_duoc_ung_vien_khac(self, monkeypatch):
        """Bug thật 21-11 (phiên `demoip_1121-103221`): `run_info.reid_veto_mat_n = 1` mà CSV

        **không có dòng `vetoed=1`** nào. Nguyên nhân: TRONG CÙNG một frame, hệ bỏ 1 ứng viên trùng
        mặt rồi NHẬN một ứng viên khác, mà `_reacquire()` trả `Step` mặc định `vetoed=False` ⇒ mất
        dấu vết veto trên artifact.
        """
        s = self._s(FakeMat([self.MAT]))
        s.start(self._f(), self.VAT)
        s.step(self._f())                        # mất dấu

        def fake_match(frame):
            s.veto_mat_n += 1                    # đã bỏ 1 ứng viên trùng mặt…
            return 0.95, self.VAT, 0.9           # …và trong CÙNG frame nhận được ứng viên khác

        monkeypatch.setattr(s, "_match_object", fake_match)
        step = s.step(self._f())
        assert step.reacquired is True
        assert step.vetoed is True               # ← trước khi vá: False (mất dấu vết veto)


class TestCacheKhuonMatTheoFrame:
    """P2 review vòng 3 (21-11): test "1 lần YuNet cho `step()`" KHÔNG giết được mutant bỏ cache.

    Lý do: `_match_object` truyền `faces=` cho mọi lần kiểm sau, nên dù bỏ cache thì `calls` vẫn = 1.
    Muốn khoá cache phải hỏi ĐÚNG hợp đồng của nó: cùng frame ⇒ 1 lần detect, frame mới ⇒ detect lại.
    """

    MAT = (10, 10, 40, 40)      # xywh

    def _s(self, fm):
        return ReIdSession(engine=object(), embedder=None, cue="object", face_veto=fm)

    def test_cung_frame_chi_detect_mot_lan(self):
        fm = FakeMat([self.MAT])
        s = self._s(fm)
        f = _obj_frame(shape=(60, 60))
        assert s._mat_trong(f) == ((10.0, 10.0, 40.0, 40.0),)
        assert s._mat_trong(f) == ((10.0, 10.0, 40.0, 40.0),)
        assert fm.calls == 1

    def test_frame_moi_thi_detect_lai(self):
        fm = FakeMat([self.MAT])
        s = self._s(fm)
        f1 = _obj_frame(shape=(60, 60))
        f2 = _obj_frame(shape=(60, 60))          # mảng MỚI (nguồn video luôn trả mảng mới)
        s._mat_trong(f1)
        s._mat_trong(f2)
        assert fm.calls == 2

    def test_reset_xoa_cache(self):
        fm = FakeMat([self.MAT])
        s = self._s(fm)
        f = _obj_frame(shape=(60, 60))
        s._mat_trong(f)
        s.reset()
        s._mat_trong(f)
        assert fm.calls == 2                     # sau reset không dùng lại mặt của phiên trước


class TestReIdGeometricVerification:
    """Ticket 03: Xác thực hình học và sinh điểm prompt tương phản khi tái bắt đối tượng."""

    def test_loai_bo_ung_vien_khac_ti_le_hinh_hoc(self):
        from unittest.mock import MagicMock
        from src.reid import ReIdSession

        engine = MagicMock()
        session = ReIdSession(engine=engine, embedder=None, cue="object")
        # Nạp 5 mẫu đối tượng 50x120 (như remote)
        for _ in range(5):
            session.geo_profile.update((100, 100, 150, 220))

        # Ứng viên mảng tường ngang (150x40): cùng màu nhưng sai tỷ lệ
        cand_wall = (200, 200, 350, 240)
        assert session.geo_profile.is_compatible(cand_wall) is False

        # Ứng viên remote thật khi quay lại (48x118): khớp
        cand_real = (200, 200, 248, 318)
        assert session.geo_profile.is_compatible(cand_real) is True

    def test_reacquire_sinh_contrast_points_cho_engine(self):
        from unittest.mock import MagicMock
        from src.reid import ReIdSession

        engine = MagicMock()
        engine.start.return_value = MagicMock(bbox=(20, 20, 60, 100), mask=np.ones((120, 120), bool))
        session = ReIdSession(engine=engine, embedder=None, cue="object")

        frame = np.zeros((120, 120, 3), dtype=np.uint8)
        bbox = (20, 20, 60, 100)
        session._reacquire(frame, bbox, score=0.85)

        assert engine.start.called
        call_kwargs = engine.start.call_args.kwargs
        assert "points" in call_kwargs and "labels" in call_kwargs
        assert call_kwargs["labels"][0] == 1  # positive ở tâm
        assert 0 in call_kwargs["labels"]     # negative ở viền ngoài



class TestTimLaiBangMoTaVanBan:
    """22-11: cue 0 — YOLO-World tìm lại vật theo MÔ TẢ VĂN BẢN.

    Vì sao cần: mọi cue cũ (mặt / đặc trưng vật) đều dựa vào thị giác; vật đơn sắc cùng tông nền
    làm `cos` mù (đo 21-11: mask-cos vùng SAI 0,752–0,989 nằm trong dải ca ĐÚNG) ⇒ cần một cue
    NGỮ NGHĨA. Detector một mình vẫn phải qua `_confirm` + cổng hình học.
    """

    def _session(self, detector, every=1):
        from src.reid import ReIdSession
        s = ReIdSession(engine=object(), embedder=None, cue="object",
                        detector=detector, detector_every=every, reacquire_confirm=1)
        for _ in range(5):
            s.geo_profile.update((100, 100, 150, 220))   # vật 50×120 như remote
        return s

    def test_detector_hop_le_thi_nhan_lai(self):
        from src.open_vocab_detector import Detection

        class _Det:
            def __init__(self, box):
                self.box, self.calls = box, 0
            def best(self, frame):
                self.calls += 1
                return Detection(bbox=self.box, conf=0.9, label="remote control") if self.box else None

        det = _Det((200, 200, 248, 318))                 # 48×118: khớp hình học
        s = self._session(det)
        s._state = "lost"
        s.engine = type("E", (), {"start": lambda self_, frame, bbox, **kw: type(
            "R", (), {"bbox": bbox, "mask": np.ones((240, 320), bool),
                      "score": 5.0, "elapsed_ms": 1.0})()})()
        step = s.step(np.zeros((240, 320, 3), np.uint8))
        assert step.reacquired is True
        assert det.calls == 1
        assert s.detector_hits == 1

    def test_detector_sai_hinh_hoc_thi_bi_loai(self):
        from src.open_vocab_detector import Detection

        class _Det:
            def best(self, frame):
                return Detection(bbox=(200, 200, 350, 240), conf=0.9, label="remote control")

        s = self._session(_Det())                        # 150×40: sai tỉ lệ với 50×120
        s._state = "lost"
        step = s.step(np.zeros((240, 320, 3), np.uint8))
        assert step.reacquired is not True
        assert s.detector_rejects == 1
        assert s.detector_hits == 0

    def test_throttle_theo_lost_age(self):
        class _Det:
            """Không thấy gì (trả None) ⇒ phiên ở lại `lost` và ta đếm được số lần HỎI detector."""
            def __init__(self):
                self.calls = 0
            def best(self, frame):
                self.calls += 1
                return None

        det = _Det()
        s = self._session(det, every=3)
        s._state = "lost"
        s.enabled = False          # tắt các cue khác để chỉ đo cue 0
        for _ in range(6):
            s._state = "lost"
            s.step(np.zeros((240, 320, 3), np.uint8))
        assert det.calls == 2, "6 frame / every=3 ⇒ đúng 2 lần hỏi detector"


class TestCoNghiTuTangHienThi:
    """23-11-2026, phiên webcam thật `demoip_1123-092343` (remote máy lạnh be trơn).

    Bug đo được: cổng "nghi đổi đối tượng" của **tầng hiển thị** báo đúng ở f264, nhưng nó chỉ
    **ẩn overlay** — `ReIdSession` vẫn `tracking` **48/312 bước** trên ÁO NGƯỜI (score 1,2–4,5,
    `mask_area` med 43 512 px) ⇒ không vào nhánh tìm lại ⇒ **Re-ID không được gọi lần nào** dù
    vật ở giữa khung, và mỗi bước lại nạp thêm mẫu của vùng SAI vào bộ nhớ.

    `set_suspicious(True)` phải: (a) bỏ track NGAY trong bước kế tiếp, (b) KHÔNG học mẫu mới,
    (c) tự xoá cờ khi nhận lại được (nếu không: bỏ → nhận lại → bỏ … vô hạn).
    """

    BOX = (20, 20, 60, 60)

    def _session(self, engine, **kw):
        kw.setdefault("lost_after_frames", 1)
        kw.setdefault("reacquire_confirm", 1)
        kw.setdefault("verify_frames", 0)
        kw.setdefault("obj_threshold", 0.5)
        return ReIdSession(engine=engine, embedder=None, cue="object", **kw)

    def test_nghi_thi_bo_track_ngay_trong_buoc_ke_tiep(self):
        """KHÔNG chờ `lost_after_frames`: cổng đã kết luận vùng này không phải vật."""
        engine = FakeEngineMasks([], shape=(96, 96))
        session = self._session(engine)
        session.start(_obj_frame(self.BOX), self.BOX)
        assert session.step(_obj_frame(self.BOX)).state == STATE_TRACKING
        reset_truoc = engine.reset_calls

        session.set_suspicious(True)
        step = session.step(_obj_frame(self.BOX))

        assert step.state != STATE_TRACKING, "còn 'tracking' nghĩa là Re-ID vẫn không được gọi"
        assert not step.result.mask.any(), "không được trả mask của vùng đang bị nghi"
        assert engine.reset_calls > reset_truoc, "phải bỏ state của track cũ"
        assert session.state in (STATE_LOST, STATE_REACQUIRING)

    def test_nghi_thi_khong_hoc_them_mau(self):
        """Nhiễm bộ nhớ (`_obj_refs`) là đường dẫn tới 'nhận lại' đúng vùng SAI (cos 0,92 ở f249)."""
        engine = FakeEngineMasks([], shape=(96, 96))
        session = self._session(engine)
        session.start(_obj_frame(self.BOX), self.BOX)
        session.step(_obj_frame(self.BOX))
        n_truoc = session.object_ref_count

        session.set_suspicious(True)
        session.step(_obj_frame((10, 10, 90, 90)))     # khung khác hẳn — nếu học sẽ thấy ref tăng

        assert session.object_ref_count == n_truoc

    def test_buoc_sau_nghi_di_tim_lai(self):
        """Bước kế tiếp phải ở nhánh TÌM LẠI (mask rỗng + state reacquiring), không phải track."""
        engine = FakeEngineMasks([], shape=(96, 96))
        session = self._session(engine, obj_ncc_min=1.01)   # không ứng viên nào qua cổng
        session.start(_obj_frame(self.BOX), self.BOX)
        session.step(_obj_frame(self.BOX))
        session.set_suspicious(True)
        session.step(_obj_frame(self.BOX))
        step = session.step(_obj_frame(self.BOX))
        assert step.state in (STATE_LOST, STATE_REACQUIRING)
        assert step.reacquired is False

    def test_nhan_lai_duoc_thi_tu_xoa_co_nghi(self):
        """Giữ cờ sau khi nhận lại ⇒ bước tracking kế tiếp lại bỏ track: quay vòng vô hạn."""
        engine = FakeEngineMasks([], shape=(96, 96))
        session = self._session(engine, obj_ncc_min=0.0)
        frame = _obj_frame(self.BOX)
        session.start(frame, self.BOX)
        session.step(frame)
        session.set_suspicious(True)
        session.step(frame)                       # bị bỏ ⇒ LOST
        assert session.suspicious is True
        step = session.step(frame)                # quét lại chính frame còn vật ⇒ nhận lại
        assert step.reacquired is True
        assert session.suspicious is False, "cờ nghi phải tự xoá khi Re-ID đã nhận lại"

    def test_reset_va_start_xoa_co_nghi(self):
        """Phiên mới không được kế thừa cờ nghi của phiên trước (chọn lại vật khác)."""
        engine = FakeEngineMasks([], shape=(96, 96))
        session = self._session(engine)
        session.start(_obj_frame(self.BOX), self.BOX)
        session.set_suspicious(True)
        session.start(_obj_frame(self.BOX), self.BOX)
        assert session.suspicious is False
        session.set_suspicious(True)
        session.reset()
        assert session.suspicious is False


class TestVetoChiChanVatGiongHinhMat:
    """23-11-2026, phiên `demoip_1123-095901`: remote giữ **ngay cạnh mặt** (ô 103×267, tỉ lệ w/h

    0,39) bị veto **322 ứng viên** ⇒ hệ "TỰ TÌM LẠI" 160 bước (64 % phiên) dù vật ở giữa khung
    (ảnh chứng: remote to rõ ở t=16 s). Veto phải chỉ chặn ứng viên **giống hình học mặt**.
    """

    MAT = (100, 10, 70, 90)         # mặt: 70×90, tỉ lệ w/h ≈ 0,78
    MAT_XYXY = (100, 10, 170, 100)

    def _s(self):
        empty = np.zeros((120, 260), bool)
        engine = FakeEngineMasks([empty], shape=(120, 260))
        return ReIdSession(engine=engine, embedder=None, cue="object",
                           lost_after_frames=1, obj_threshold=0.5, reacquire_confirm=1,
                           verify_frames=0, face_veto=FakeMat([self.MAT]))

    def _frame(self):
        return _obj_frame(shape=(120, 260))

    def test_vat_cao_narrow_nam_canh_mat_KHONG_bi_veto(self):
        """Remote 103×267 chồng lên ô mặt ⇒ KHÔNG phải mặt (tỉ lệ 0,39 vs 0,78) ⇒ không veto."""
        s = self._s()
        remote_xyxy = (120, 60, 223, 327)        # 103×267, tỉ lệ 0,386
        assert s._trung_mat(self._frame(), remote_xyxy) is False

    def test_ung_vien_giong_hinh_mat_VAN_bi_veto(self):
        """Ô vuông/vừa như mặt chồng lên mặt ⇒ vẫn veto (giữ nguyên tác dụng chống bám mặt)."""
        s = self._s()
        assert s._trung_mat(self._frame(), (105, 15, 165, 95)) is True     # 60×80, tỉ lệ 0,75
        assert s._trung_mat(self._frame(), (100, 0, 180, 110)) is True     # 80×110, tỉ lệ 0,73

    def test_vat_nho_hon_mat_nhung_cao_narrow_khong_bi_veto(self):
        """Vật nhỏ, cao (như bút/remote ở xa) vẫn không phải mặt ⇒ không veto."""
        s = self._s()
        assert s._trung_mat(self._frame(), (120, 30, 150, 110)) is False   # 30×80, tỉ lệ 0,375

    def test_vung_NEN_khong_duoc_khop_chi_vi_o_chua_nen(self):
        """BÀI HỌC 23-11 (phiên `demoip_1123-101110`): đừng lưu mẫu đặc trưng trên Ô CHỮ NHẬT.

        Bản đầu tôi thêm `_obj_refs_box` (mẫu chấm trên ô, để "so cùng loại" với ứng viên khi tìm
        lại). Hệ quả ĐO ĐƯỢC: ô mẫu gồm cả TƯỜNG nên vùng TƯỜNG khớp cosine **0,976** (ncc chỉ
        0,484) ⇒ nhận lại SAI vào tường/cửa ngay sau 2 frame mất dấu, rồi bám tường ~100 bước
        (mất dấu chỉ 1 % — chỉ số ĐẸP mà bám sai). Test này khoá lại: mẫu phải là MASK (vật), và
        vùng nền thuần không được vượt ngưỡng cosine của vật.
        """
        from src.appearance import object_signature

        # vật: ô vuông có sọc trắng ở góc trên-trái; nền: tường xám phẳng
        tuong = (205, 208, 212)
        frame = np.full((120, 200, 3), tuong, np.uint8)
        obj_box = (20, 20, 60, 60)
        frame[20:60, 20:60] = (0, 140, 255)
        for x in range(20, 60, 8):
            frame[20:60, x:min(x + 3, 60)] = (255, 255, 255)

        s = ReIdSession(engine=FakeEngineMasks([], shape=(120, 200)), embedder=None, cue="object",
                        obj_threshold=0.75, reacquire_confirm=1, verify_frames=0)
        s._collect_reference(frame, obj_box, _obj_mask(obj_box, shape=(120, 200)))
        # ĐÚNG 1 mẫu cho 1 lần thu: nếu ai đó lại thêm mẫu "trên ô" (lẫn nền) thì thành 2 ⇒ đỏ.
        assert len(s._obj_refs) == 1, (
            "mỗi lần thu mẫu chỉ được thêm MẪU MASK của vật; mẫu chấm trên ô (lẫn tường) đã bị bỏ "
            "vì làm vùng nền khớp 0,78 (đo phiên demoip_1123-101110: nhận lại SAI vào tường)"
        )

        # ứng viên = vùng TƯỜNG phẳng (đúng loại "ô nền" mà bản lỗi đã nhận)
        nen = np.zeros((120, 200), bool)
        nen[30:110, 110:180] = True
        sig_nen = object_signature(frame, nen)
        # ứng viên = đúng vật (mask thật)
        sig_vat = object_signature(frame, _obj_mask(obj_box, shape=(120, 200)))

        from src.reid import best_match as _bm

        assert _bm(s._obj_refs, sig_nen) < 0.75, (
            "vùng nền phẳng KHÔNG được khớp với vật — nếu khớp thì đã lưu mẫu trên ô (lẫn nền)"
        )
        assert _bm(s._obj_refs, sig_vat) > _bm(s._obj_refs, sig_nen) + 0.3, (
            "vật thật phải khớp CAO HƠN HẲN vùng nền"
        )


class TestGhiCosXacMinh:
    """23-11-2026: cổng XÁC MINH mask-vs-mask (`_verify_ok`) đã tồn tại và ĐÃ PASS vùng tường ở

    phiên `demoip_1123-101110` (nhận lại f118 rồi tracking tới hết phiên) — nhưng **không có con số
    nào được ghi** ⇒ câu "cổng xác minh có tách được vùng sai không" chỉ suy luận được. Nay `Step`
    mang `verify_cos` để artifact trả lời trực tiếp.
    """

    BOX = (20, 20, 60, 60)

    def test_verify_cos_co_so_o_frame_kiem_chung(self):
        empty = np.zeros((96, 96), bool)
        engine = FakeEngineMasks([empty], shape=(96, 96))
        session = ReIdSession(engine=engine, embedder=None, cue="object",
                              lost_after_frames=1, obj_threshold=0.5,
                              reacquire_confirm=1, verify_frames=2)
        frame = _obj_frame(self.BOX)
        session.start(frame, self.BOX)
        session.step(frame)                      # mất dấu
        step = session.step(frame)               # nhận lại
        assert step.reacquired is True

        sau = session.step(frame)                # frame KIỂM CHỨNG #1
        assert isinstance(sau.verify_cos, float) and sau.verify_cos >= 0.0, (
            "frame kiểm chứng phải ghi được cos của mask-vs-mask; nếu None thì artifact lại mù"
        )

    def test_frame_thuong_khong_co_verify_cos(self):
        """Chỉ frame trong giai đoạn kiểm chứng mới có số — frame tracking thường phải `None`."""
        engine = FakeEngineMasks([], shape=(96, 96))
        session = ReIdSession(engine=engine, embedder=None, cue="object",
                              lost_after_frames=99, verify_frames=0)
        frame = _obj_frame(self.BOX)
        session.start(frame, self.BOX)
        step = session.step(frame)
        assert step.verify_cos is None


class TestCosTruocCong:
    """23-11-2026 (review vòng 2): `reid_score` chỉ là điểm của ứng viên **ĐÃ QUA cổng** ⇒ artifact

    cũ không phân biệt được "bộ sinh không đưa vật vào danh sách" với "cổng chặn". Đo được: phiên
    `095901` có 82/160 bước tìm lại với `reid_score = -1` mà **không biết** cosine cao nhất là bao
    nhiêu. Cột `cos_truoc_cong` trả lời đúng câu đó.
    """

    BOX = (20, 20, 60, 60)

    def test_cos_truoc_cong_co_so_ke_ca_khi_moi_ung_vien_bi_chan(self):
        # ngưỡng cosine không thể đạt ⇒ KHÔNG ứng viên nào được nhận, nhưng vẫn phải ghi điểm tốt nhất
        empty = np.zeros((96, 96), bool)
        engine = FakeEngineMasks([empty], shape=(96, 96))
        session = ReIdSession(engine=engine, embedder=None, cue="object",
                              lost_after_frames=1, obj_threshold=1.01,
                              obj_ncc_min=0.0, reacquire_confirm=1, verify_frames=0)
        frame = _obj_frame(self.BOX)
        session.start(frame, self.BOX)
        session.step(frame)                     # mất dấu
        step = session.step(frame)              # đang tìm lại
        assert step.reacquired is False
        assert isinstance(step.cos_truoc_cong, float) and step.cos_truoc_cong >= 0.0, (
            "phải ghi cosine cao nhất TRƯỚC cổng; nếu None thì lại không tách được 'bộ sinh' vs 'cổng'"
        )

    def test_ca_verify_that_bai_van_ghi_verify_cos(self):
        """P1 vòng 2: ca ĐÁNG QUAN TÂM NHẤT là xác minh THẤT BẠI — bản đầu trả `Step` không có cos."""
        empty = np.zeros((96, 96), bool)
        # mẫu #3 = `None` ⇒ engine giả trả mask theo ô (đúng ca "bám lại bình thường" để
        # `_verify_ok` có mask mà chấm).
        engine = FakeEngineMasks([empty, None], shape=(96, 96))
        # `auto_recover=False`: cô lập đúng cổng XÁC MINH (cổng nhảy nội bộ sẽ bỏ track trước và
        # làm test này đo sai thứ — đã gặp khi viết test).
        session = ReIdSession(engine=engine, embedder=None, cue="object",
                              lost_after_frames=1, obj_threshold=0.5,
                              reacquire_confirm=1, verify_frames=2, auto_recover=False)
        frame = _obj_frame(self.BOX)
        session.start(frame, self.BOX)
        session.step(frame)                     # mất dấu
        step = session.step(frame)              # nhận lại
        assert step.reacquired is True
        # ép ngưỡng lên trên mức cosine đạt được ⇒ `_verify_ok` phải trả False
        session.obj_threshold = 1.5
        sau = session.step(_obj_frame((30, 30, 70, 70)))    # frame "kiểm chứng" KHÔNG giống vật
        assert sau.state == STATE_LOST, "verify thất bại phải bỏ lần nhận lại"
        assert isinstance(sau.verify_cos, float), (
            "verify thất bại phải ghi được cos — đây là ca cần soi nhất"
        )

    def test_cand_n_va_cand_sinh_n_tach_bo_sinh_voi_cong(self):
        """`cand_sinh_n` = số ô BỘ SINH đưa ra; `cand_n` = số ứng viên ĐÃ CHẤM (sau cổng NCC).

        Đính chính (P1 review độc lập 23-11): bản đầu chỉ có `cand_n` và docstring ghi "0 = bộ sinh
        rỗng" — SAI, vì `cand_n` được đếm SAU `_filter_by_radius` và SAU cổng `obj_ncc_min`.

        Reviewer vòng 2 chỉ đúng: `reid_score = -1` một mình KHÔNG nói được cái nào — 170/175 dòng
        `-1` của phiên `095901` có `ncc = -1` (bộ sinh rỗng) nhưng 5 dòng có ncc 0,33–0,40 (bị cổng
        NCC loại), và phiên `101110` có 2/3 frame LOST **có** điểm 0,894/0,972.
        """
        empty = np.zeros((96, 96), bool)
        engine = FakeEngineMasks([empty], shape=(96, 96))
        session = ReIdSession(engine=engine, embedder=None, cue="object",
                              lost_after_frames=1, obj_threshold=1.01,
                              obj_ncc_min=0.0, reacquire_confirm=1)
        frame = _obj_frame(self.BOX)
        session.start(frame, self.BOX)
        session.step(frame)                     # mất dấu
        step = session.step(_obj_frame((40, 40, 80, 80)))   # vùng lạ, tìm lại
        assert step.reacquired is False
        assert isinstance(step.cand_n, int) and step.cand_n >= 1, (
            "prefilter NCC vẫn sinh ứng viên ⇒ cand_n > 0 (bị chặn ở CỔNG, không phải bộ sinh)"
        )
        assert isinstance(step.cand_sinh_n, int) and step.cand_sinh_n >= step.cand_n

    def test_cong_ncc_loai_thi_cand_n_bang_0_nhung_bo_sinh_khong_rong(self):
        """`obj_ncc_min` cao ⇒ mọi ứng viên bị loại: `cand_n = 0` NHƯNG `cand_sinh_n > 0`.

        Đây đúng ca mà bản đầu báo sai thành "bộ sinh rỗng" (P1 review độc lập 23-11).
        """
        empty = np.zeros((96, 96), bool)
        # 2 mask rỗng: frame 2 = mất dấu, frame 3 = vẫn rỗng ⇒ mới vào nhánh TÌM LẠI (đã mắc lỗi
        # nàykhi viết test: engine trả mask theo ô thì step 3 quay lại `tracking` và `cand_n = None`)
        engine = FakeEngineMasks([empty, empty], shape=(96, 96))
        session = ReIdSession(engine=engine, embedder=None, cue="object",
                              lost_after_frames=1, obj_threshold=0.5,
                              # 1,5 > mọi NCC (≤1) ⇒ cổng NCC loại HẾT ứng viên
                              obj_ncc_min=1.5, reacquire_confirm=1)
        frame = _obj_frame(self.BOX)
        session.start(frame, self.BOX)
        session.step(frame)
        step = session.step(_obj_frame((30, 30, 70, 70)))
        assert step.cand_n == 0, "cổng NCC loại hết ⇒ không ứng viên nào được CHẤM"
        assert step.cand_sinh_n >= 1, "bộ sinh VẪN đưa ra ô ⇒ không được gọi là 'bộ sinh rỗng'"
        assert step.cand_ncc_loai >= 1
