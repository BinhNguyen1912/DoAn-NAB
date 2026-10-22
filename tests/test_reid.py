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
