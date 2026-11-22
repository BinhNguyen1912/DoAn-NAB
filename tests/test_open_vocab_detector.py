"""Test `src.open_vocab_detector` — bọc YOLO-World, KHÔNG tải model thật.

Vì sao phải ghim bằng test: đây là phụ thuộc TUỲ CHỌN (thiếu `ultralytics` hoặc thiếu weights là
chuyện bình thường trên máy khác/CI). Nếu nó ném thay vì fail-open thì một tính năng phụ làm chết
phiên live — đúng loại lỗi đã gặp với `samurai` (ticket: import lỗi ở CI).
"""

import numpy as np
import pytest

from src.open_vocab_detector import DEFAULT_CONF, Detection, OpenVocabDetector


class _Box:
    """Giả lập `Results.boxes` của ultralytics cho 1 box."""

    def __init__(self, xyxy, conf, cls):
        self.xyxy = [xyxy]
        self.conf = [conf]
        self.cls = [cls]


class _Result:
    def __init__(self, boxes, names=None):
        self.boxes = boxes
        self.names = names or {0: "remote control"}


class _FakeYolo:
    """Thay `ultralytics.YOLO` — ghi lại tham số và trả kết quả dựng sẵn."""

    instances: list = []

    def __init__(self, weights):
        self.weights = weights
        self.classes: list[str] = []
        self.raise_on_predict: Exception | None = None
        self.result = _Result([])
        self.predict_calls: list[dict] = []
        _FakeYolo.instances.append(self)

    def set_classes(self, classes):
        self.classes = list(classes)

    def predict(self, frame, **kwargs):
        self.predict_calls.append(kwargs)
        if self.raise_on_predict is not None:
            raise self.raise_on_predict
        return [self.result]


@pytest.fixture
def fake_ultralytics(monkeypatch, tmp_path):
    """Cài `ultralytics` giả vào `sys.modules` + tạo file weights rỗng để `available = True`."""
    import sys
    import types

    _FakeYolo.instances.clear()
    module = types.ModuleType("ultralytics")
    module.YOLO = _FakeYolo
    monkeypatch.setitem(sys.modules, "ultralytics", module)
    weights = tmp_path / "yolov8s-worldv2.pt"
    weights.write_bytes(b"fake")
    return weights


class TestTrangThai:
    def test_thieu_weights_thi_khong_available_va_detect_rong(self, tmp_path):
        det = OpenVocabDetector(weights=str(tmp_path / "khong-co.pt"))
        assert det.available is False
        assert det.detect(np.zeros((10, 10, 3), np.uint8)) == []
        assert det.last_error is not None and "weights" in det.last_error
        assert det.calls == 0        # KHÔNG đếm là "đã đo"

    def test_thieu_ultralytics_thi_load_tra_false_khong_nem(self, fake_ultralytics, monkeypatch):
        import sys

        monkeypatch.setitem(sys.modules, "ultralytics", None)   # import sẽ ném ImportError
        det = OpenVocabDetector(weights=str(fake_ultralytics), classes=("remote control",))
        assert det.load() is False
        assert det.last_error is not None
        assert det.detect(np.zeros((8, 8, 3), np.uint8)) == []


class TestSuyLuan:
    def test_truyen_dung_tham_so_va_doi_toa_do_sang_int(self, fake_ultralytics):
        det = OpenVocabDetector(weights=str(fake_ultralytics), classes=("remote control",),
                                conf=0.4, imgsz=320)
        assert det.load() is True
        model = _FakeYolo.instances[-1]
        assert model.classes == ["remote control"]
        model.result = _Result([_Box([10.4, 20.6, 30.5, 40.5], 0.9, 0)])

        found = det.detect(np.zeros((100, 100, 3), np.uint8))

        assert found == [Detection(bbox=(10, 21, 30, 40), conf=pytest.approx(0.9),
                                   label="remote control")]
        call = model.predict_calls[-1]
        assert call["imgsz"] == 320 and call["conf"] == 0.4
        assert call["verbose"] is False
        assert det.calls == 1
        assert det.last_ms is not None and det.last_ms >= 0

    def test_sap_xep_conf_giam_dan_va_best_lay_dau(self, fake_ultralytics):
        det = OpenVocabDetector(weights=str(fake_ultralytics), classes=("remote control",))
        det.load()
        _FakeYolo.instances[-1].result = _Result([
            _Box([0, 0, 10, 10], 0.31, 0),
            _Box([50, 50, 90, 90], 0.88, 0),
        ])
        frame = np.zeros((100, 100, 3), np.uint8)

        assert [d.conf for d in det.detect(frame)] == [0.88, 0.31]
        assert det.best(frame).bbox == (50, 50, 90, 90)

    def test_predict_nem_thi_tra_rong_va_ghi_loi(self, fake_ultralytics):
        det = OpenVocabDetector(weights=str(fake_ultralytics), classes=("remote control",))
        det.load()
        _FakeYolo.instances[-1].raise_on_predict = RuntimeError("CUDA out of memory")

        assert det.detect(np.zeros((10, 10, 3), np.uint8)) == []
        assert "CUDA out of memory" in (det.last_error or "")
        assert det.calls == 0

    def test_nguong_mac_dinh_khong_qua_thap(self):
        # Đo trên `binh1` 22-11: dương tính giả ở conf 0,29–0,30 ⇒ 0,25 là quá thấp.
        assert DEFAULT_CONF >= 0.30
