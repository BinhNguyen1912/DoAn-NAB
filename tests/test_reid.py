"""Test module tái nhận diện (ADR-0003, ticket 09) — hàm thuần + máy trạng thái với engine giả.

Không cần model/SAM 2: engine và embedder đều là fake duck-type.
"""
import numpy as np
import pytest

from src.reid import (
    STATE_LOST,
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
    """

    def __init__(self, masks, shape=(96, 96)):
        self._masks = list(masks)
        self._shape = tuple(shape)
        self.start_calls = []
        self.process_calls = 0

    def _box_mask(self, bbox):
        m = np.zeros(self._shape, bool)
        x1, y1, x2, y2 = [int(v) for v in bbox]
        m[max(0, y1):min(y2, self._shape[0]), max(0, x1):min(x2, self._shape[1])] = True
        return m

    def _result(self, mask, bbox):
        return type("R", (), {"frame_idx": 0, "mask": mask, "bbox": bbox,
                              "score": 1.0, "elapsed_ms": 1.0})()

    def start(self, frame, bbox):
        self.start_calls.append(tuple(bbox))
        return self._result(self._box_mask(bbox), bbox)

    def process(self, frame):
        self.process_calls += 1
        nxt = self._masks.pop(0) if self._masks else None
        if nxt is None:
            return self._result(self._box_mask((10, 10, 50, 50)), (10, 10, 50, 50))
        return self._result(nxt, (10, 10, 50, 50))


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
                              lost_after_frames=1)
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
                              lost_after_frames=1)
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
                              lost_after_frames=1, obj_threshold=0.6)
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
                           obj_ncc_min=ncc_min)

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
