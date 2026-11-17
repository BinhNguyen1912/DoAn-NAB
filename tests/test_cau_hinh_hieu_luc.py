"""`status.json` echo cấu hình phiên + tự kiểm **"yêu cầu == hiệu lực"** (Next steps 14-11).

Vì sao cần: `--image-size 192` chỉ là **yêu cầu**. Hydra override có thể không được áp (khoá đổi
tên, `model_cfg` bỏ qua, worker bản cũ) ⇒ model chạy 1024 mà không báo gì, và mọi số trong bảng cấu
hình bị gán cho một cấu hình model **không hề chạy**. Trước 14-11 artifact không có cách nào kiểm
điều đó: nó chỉ chép lại tham số CLI (đúng loại "xanh giả" mà repo đã gặp nhiều lần).

Ghìm ở đây:
- `image_size_hieu_luc = None` = **chưa kiểm được** ⇒ KHÔNG được đọc thành "khớp";
- lệch ⇒ `cau_hinh_lech` có phần tử, `scripts/bang_cau_hinh._run_once` từ chối dòng đó (không lặng lẽ
  đưa số vào bảng);
- giai đoạn `loading` (chưa có engine) vẫn ghi cấu hình ĐỊNH chạy;
- hai định nghĩa tuổi mask phải được khai ngay trong file (AGENTS §6).
"""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import bang_cau_hinh as bch
from src.live_tracking import (
    DINH_NGHIA_TUOI_MASK,
    STATUS_NAME,
    LiveTrackConfig,
    LiveTrackStats,
    LiveTrackingSession,
    cau_hinh_hieu_luc,
    cau_hinh_yeu_cau,
    so_khop_cau_hinh,
    status_payload,
)


class _Engine:
    """Engine giả tối thiểu: chỉ cần `image_size` (yêu cầu) + `image_size_hieu_luc` (thật chạy)."""

    def __init__(self, image_size=192, hieu_luc=192):
        self.image_size = image_size
        if hieu_luc is not None:
            self.image_size_hieu_luc = hieu_luc


def _session(tmp_path, engine) -> LiveTrackingSession:
    return LiveTrackingSession(engine, LiveTrackConfig(source="0", out_dir=tmp_path))


class TestCauHinhYeuCau:
    def test_giu_du_khoa_va_image_size_none_la_mac_dinh(self):
        ch = cau_hinh_yeu_cau(source="data/binh1.mp4", image_size=None, vos_every=3,
                              display_fps=30.0, mask_smoothing=1.0, device="cpu")
        assert ch["image_size_yeu_cau"] is None, "None = KHÔNG override (1024 của model_cfg)"
        assert ch["vos_every"] == 3 and ch["display_fps"] == 30.0
        assert ch["device"] == "cpu"

    def test_khai_dinh_nghia_tuoi_mask(self):
        ch = cau_hinh_yeu_cau()
        assert ch["mask_age_dinh_nghia"] == DINH_NGHIA_TUOI_MASK
        assert "mask_age_total_ms" in ch["mask_age_dinh_nghia"]
        assert "CŨ" in ch["mask_age_dinh_nghia"], "phải nói rõ đây KHÔNG phải định nghĩa cũ"
        # Câu định nghĩa phải mô tả ĐÚNG hành vi hiện tại: từ ticket #24, `vos_every=1` (đơn luồng)
        # CŨNG đo tuổi mask (age = 0 vì frame vừa VOS chính là frame đang phát). Bản cũ ghim
        # "vos_every=1 ⇒ age_n = 0" — mâu thuẫn với chính artifact `bangcau --every 1` (age_n = 60)
        # mà test vẫn xanh vì chỉ kiểm chuỗi con "age_n" (P1 review độc lập 17-11).
        assert "vos_every=1" in ch["mask_age_dinh_nghia"]
        assert "age = 0" in ch["mask_age_dinh_nghia"], (
            "phải nói rõ đường đơn luồng có age = 0 chứ không phải 'age_n = 0' (chưa đo)")
        assert "không nội suy LK" in ch["mask_age_dinh_nghia"], (
            "phải nói rõ vos_every=1 KHÔNG có drift_iou (đừng để người sau 'sửa' bằng cách đo drift)")

    def test_ep_so_nguyen_cho_image_size(self):
        """`--image-size` từ API có thể là chuỗi số ⇒ echo phải chuẩn hoá, không ghi `\"192\"`."""
        ch = cau_hinh_yeu_cau(image_size="192")
        assert ch["image_size_yeu_cau"] == 192


class TestSoKhop:
    def test_khop_thi_danh_sach_rong(self):
        ch = cau_hinh_hieu_luc(cau_hinh_yeu_cau(image_size=192), _Engine(192, 192))
        assert ch["image_size_hieu_luc"] == 192
        assert ch["image_size_kiem_duoc"] is True
        assert so_khop_cau_hinh(ch) == []

    def test_override_khong_co_tac_dung_thi_bao_lech(self):
        """Ca thật cần chặn: yêu cầu 192 nhưng predictor chạy 1024 (hydra override no-op)."""
        ch = cau_hinh_hieu_luc(cau_hinh_yeu_cau(image_size=192), _Engine(192, 1024))
        assert ch["image_size_kiem_duoc"] is True
        assert so_khop_cau_hinh(ch) == ["image_size"]

    def test_hieu_luc_none_la_chua_kiem_duoc_khong_phai_khop(self):
        ch = cau_hinh_hieu_luc(cau_hinh_yeu_cau(image_size=192), _Engine(192, None))
        assert ch["image_size_hieu_luc"] is None
        assert ch["image_size_kiem_duoc"] is False, "cờ tường minh: cấm đọc `lech == []` thành 'khớp'"
        assert so_khop_cau_hinh(ch) == [], "chưa đo được thì không được bịa là lệch"

    def test_yeu_cau_none_thi_khong_so(self):
        """`image_size=None` = dùng mặc định model (1024) ⇒ không có gì để so, dù hiệu lực là 1024."""
        ch = cau_hinh_hieu_luc(cau_hinh_yeu_cau(image_size=None), _Engine(None, 1024))
        assert ch["image_size_hieu_luc"] == 1024
        assert so_khop_cau_hinh(ch) == []

    @pytest.mark.parametrize("rac", ["abc", object()])
    def test_gia_tri_rac_thi_coi_la_lech(self, rac):
        ch = {"image_size_yeu_cau": rac, "image_size_hieu_luc": 192}
        assert so_khop_cau_hinh(ch) == ["image_size"]


class TestPayload:
    def test_mac_dinh_rong_chu_khong_bia_cau_hinh(self):
        payload = status_payload(LiveTrackStats())
        assert payload["cau_hinh"] == {} and payload["cau_hinh_lech"] == []

    def test_phien_echo_cau_hinh_hieu_luc(self, tmp_path):
        session = _session(tmp_path, _Engine(192, 192))
        session._publish_status(tmp_path)

        payload = json.loads((tmp_path / STATUS_NAME).read_text(encoding="utf-8"))
        assert payload["cau_hinh"]["image_size_yeu_cau"] == 192
        assert payload["cau_hinh"]["image_size_hieu_luc"] == 192
        assert payload["cau_hinh_lech"] == []

    def test_phien_lech_thi_status_noi_ra_va_canh_bao(self, tmp_path, capsys):
        session = _session(tmp_path, _Engine(192, 1024))
        session._publish_status(tmp_path)

        payload = json.loads((tmp_path / STATUS_NAME).read_text(encoding="utf-8"))
        assert payload["cau_hinh_lech"] == ["image_size"]
        assert payload["cau_hinh"]["image_size_hieu_luc"] == 1024
        assert "HIỆU LỰC" in capsys.readouterr().out, "cảnh báo phải vào log worker để người đo thấy"

    def test_trang_thai_loading_cung_ghi_cau_hinh_dinh_chay(self, tmp_path):
        """Nạp model 20–240 s: người đọc `status.json` sớm phải biết phiên sẽ chạy cấu hình nào."""
        from tools.live_worker import _write_loading

        ch = cau_hinh_yeu_cau(source="0", image_size=256, vos_every=3, device="cpu")
        _write_loading(tmp_path, "Đang nạp model...", device="cpu", cau_hinh=ch)

        payload = json.loads((tmp_path / STATUS_NAME).read_text(encoding="utf-8"))
        assert payload["state"] == "loading"
        assert payload["cau_hinh"]["image_size_yeu_cau"] == 256
        assert payload["cau_hinh"]["image_size_hieu_luc"] is None, "chưa nạp model ⇒ chưa kiểm được"
        assert set(payload) == set(status_payload(LiveTrackStats())), "một schema cho cả hai giai đoạn"


class TestArtifactTuKiem:
    """`scripts/bang_cau_hinh._run_once` (dùng chung cho `./run bangcau` và `./run ab`)."""

    def _run(self, monkeypatch, status: dict):
        def fake_run(cmd, **_kw):
            out = Path(cmd[cmd.index("--out-dir") + 1])
            (out / "status.json").write_text(json.dumps(status), encoding="utf-8")
            return SimpleNamespace(returncode=0, stdout="", stderr="")

        monkeypatch.setattr(bch.subprocess, "run", fake_run)
        return bch._run_once(Path("data/binh1.mp4"), (10, 10, 40, 40), 192, 3, 5, "cpu", 5.0)

    def test_lech_thi_la_loi_khong_vao_bang(self, monkeypatch):
        kq = self._run(monkeypatch, {
            "state": "stopped", "frames": 5, "measured_fps": 29.8,
            "cau_hinh": {"image_size_yeu_cau": 192, "image_size_hieu_luc": 1024},
            "cau_hinh_lech": ["image_size"]})
        assert "hiệu lực" in kq["loi"]
        assert "1024" in kq["loi"], "câu lỗi phải nêu giá trị model THẬT SỰ chạy"
        assert "measured_fps" not in kq, "lần chạy lệch cấu hình không được thành dòng số"

    def test_khop_thi_echo_cau_hinh_vao_dong(self, monkeypatch):
        kq = self._run(monkeypatch, {
            "state": "stopped", "frames": 5, "measured_fps": 29.8,
            "cau_hinh": {"image_size_yeu_cau": 192, "image_size_hieu_luc": 192},
            "cau_hinh_lech": []})
        assert "loi" not in kq
        assert kq["cau_hinh"]["image_size_hieu_luc"] == 192

    def test_hieu_luc_none_bi_tu_choi_du_lech_rong(self, monkeypatch):
        """P1 review 15-11: `image_size_hieu_luc = None` + `lech = []` KHÔNG phải "khớp".

        Ca thật: predictor không khai báo `image_size` (hoặc worker bản cũ không echo) ⇒ nếu chỉ tin
        `cau_hinh_lech` thì dòng "192" trong bảng có thể chứa số của model 1024.
        """
        kq = self._run(monkeypatch, {
            "state": "stopped", "frames": 5, "measured_fps": 29.8,
            "cau_hinh": {"image_size_yeu_cau": 192, "image_size_hieu_luc": None,
                         "image_size_kiem_duoc": False},
            "cau_hinh_lech": []})
        assert "KHÔNG kiểm được" in kq["loi"]
        assert "measured_fps" not in kq

    def test_worker_ban_cu_khong_echo_thi_bi_tu_choi(self, monkeypatch):
        """Worker cũ không có `cau_hinh` ⇒ không có bằng chứng ⇒ không được vào bảng."""
        kq = self._run(monkeypatch, {"state": "stopped", "frames": 5, "measured_fps": 29.8})
        assert "hiệu lực" in kq["loi"] and "None" in kq["loi"]

    def test_echo_noi_yeu_cau_khac_tham_so_benchmark_cung_bi_tu_choi(self, monkeypatch):
        """Echo tự khai `yeu_cau = null` trong khi benchmark truyền 192 ⇒ lệch, phải chặn."""
        kq = self._run(monkeypatch, {
            "state": "stopped", "frames": 5,
            "cau_hinh": {"image_size_yeu_cau": None, "image_size_hieu_luc": 1024},
            "cau_hinh_lech": []})
        assert "hiệu lực" in kq["loi"] and "1024" in kq["loi"]

    def test_tong_hop_ghi_cac_gia_tri_hieu_luc_da_thay(self):
        ok = [{"measured_fps": 29.8, "age_n": 10, "frames": 30,
               "cau_hinh": {"image_size_yeu_cau": 192, "image_size_hieu_luc": size}}
              for size in (192, 192, 1024)]
        bang = bch.tong_hop({}, [192], [3], {(192, 3): ok})
        ch = bang["192_3"]["cau_hinh"]
        assert ch["image_size_hieu_luc_da_thay"] == [192, 1024], (
            "cùng một dòng bảng mà model chạy hai độ phân giải ⇒ phải thấy trong artifact")

    def test_tong_hop_chua_kiem_duoc_thi_none_chu_khong_phai_danh_sach(self):
        """`[None]` đọc như một giá trị thật ⇒ phải là `None` (chưa kiểm được) hẳn hỏi."""
        ok = [{"measured_fps": 29.8, "age_n": 10, "frames": 30,
               "cau_hinh": {"image_size_yeu_cau": 192, "image_size_hieu_luc": None}}]
        bang = bch.tong_hop({}, [192], [3], {(192, 3): ok})
        assert bang["192_3"]["cau_hinh"]["image_size_hieu_luc_da_thay"] is None

    def test_tong_hop_khong_co_lan_nao_ok_thi_cau_hinh_rong(self):
        bang = bch.tong_hop({}, [192], [3], {(192, 3): [{"loi": "x"}]})
        assert bang["192_3"]["cau_hinh"] == {}


class TestTrackerEngine:
    def test_image_size_hieu_luc_doc_tu_predictor(self):
        from src.tracker_engine import TrackerEngine

        engine = TrackerEngine(SimpleNamespace(image_size=1024), image_size=192)
        assert engine.image_size == 192                # ĐÃ YÊU CẦU
        assert engine.image_size_hieu_luc == 1024      # THẬT SỰ chạy

    def test_predictor_khong_khai_bao_thi_none(self):
        from src.tracker_engine import TrackerEngine

        assert TrackerEngine(object(), image_size=192).image_size_hieu_luc is None
