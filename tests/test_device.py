"""
Test `src/device.py` — chuẩn hoá/kiểm tra thiết bị chạy model ở cửa vào.

Vì sao có: trước 11-11 đường live (web demo) **không** truyền `device` xuống
`TrackerEngine.build_default()` ⇒ máy có GPU vẫn chạy CPU, và mọi số FPS đo qua web bị gán sai
thiết bị trong báo cáo. Ba bẫy phải khoá bằng test:
  1. `None`/"" (không cấu hình) phải là `cpu` — không được nổ;
  2. xin `cuda` khi máy KHÔNG có CUDA phải **ném lỗi kèm hướng dẫn**, không âm thầm rơi về CPU;
  3. tên lạ (`gpu`, `cuda:1`) phải bị từ chối thay vì lọt xuống CLI.
"""

import pytest

from src.device import device_from_env, normalize_device, validate_device


class TestNormalize:
    @pytest.mark.parametrize("value", [None, "", "  "])
    def test_khong_cau_hinh_la_cpu(self, value):
        assert normalize_device(value) == "cpu"

    @pytest.mark.parametrize("value,expected", [
        ("cpu", "cpu"), ("CUDA", "cuda"), ("  Cuda  ", "cuda"),
    ])
    def test_chuan_hoa_khoang_trang_va_hoa_thuong(self, value, expected):
        assert normalize_device(value) == expected

    @pytest.mark.parametrize("value", ["gpu", "cuda:1", "mps", "cpu0"])
    def test_ten_la_bi_tu_choi(self, value):
        """Lọt tên lạ xuống CLI sẽ làm worker chết giữa lúc demo — bắt ngay ở đây."""
        with pytest.raises(ValueError, match="device phải là"):
            normalize_device(value)


class TestValidate:
    def test_cuda_co_san_thi_qua(self):
        assert validate_device("cuda", cuda_available=True) == "cuda"

    def test_cuda_khong_co_thi_bao_loi_kem_huong_dan(self):
        with pytest.raises(ValueError) as info:
            validate_device("cuda", cuda_available=False)
        message = str(info.value)
        assert "GPU CUDA" in message
        assert "T4" in message, "phải nói đường sửa (Colab → T4) chứ không chỉ 'không có GPU'"

    def test_khong_biet_cuda_thi_khong_kiem(self):
        """`cuda_available=None` = nơi không có torch (API dựng lệnh) — chỉ chuẩn hoá tên."""
        assert validate_device("cuda") == "cuda"

    def test_cpu_thi_khong_can_kiem_cuda(self):
        assert validate_device("cpu", cuda_available=False) == "cpu"


class TestDeviceFromEnv:
    def test_khong_dat_bien_la_cpu(self):
        assert device_from_env({}) == "cpu"

    def test_doc_dung_bien_moi_truong(self):
        assert device_from_env({"CAMERA_AI_DEVICE": "cuda"}) == "cuda"

    def test_go_sai_thi_no_ngay_luc_khoi_dong(self):
        """API đọc lúc dựng service ⇒ lỗi hiện khi bật server, không phải giữa buổi demo."""
        with pytest.raises(ValueError, match="device phải là"):
            device_from_env({"CAMERA_AI_DEVICE": "gpu"})
