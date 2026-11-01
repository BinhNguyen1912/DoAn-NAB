"""Test ĐỒNG BỘ ngưỡng re-ID giữa 3 nguồn sự thật — chống đúng lớp bug đã xảy ra thật.

Vì sao có file này (retro 01-11, phát hiện 2 sự cố cùng lớp):
1. **27-10**: `reid.py` truyền `min_side=24` ĐÈ mất hằng số trong `appearance.py` → bản sửa
   "vật mảnh (cây bút) lưu được mẫu" **KHÔNG có tác dụng**; chỉ phát hiện khi người dùng test webcam.
2. **01-11**: cùng một tham số `reid_obj_ncc_min` có **3 giá trị** ở 5 file — config/code = 0.0 (TẮT)
   nhưng README nói "bật mặc định 0,70", `tom-tat-do-an.md` nói 0,70, comment trong
   `configs/default.yaml` nói 0,75. Nguyên nhân: 6 lần đổi ngưỡng trong 3 ngày, mỗi lần sync tay.

Guardrail: một tham số có 4 nơi khai báo (DEFAULTS / YAML / hằng số `reid.py` / tham số
`ReIdSession`) — test này bắt buộc cả 4 khớp nhau, và tài liệu không được khẳng định sai.
"""
import re
from pathlib import Path

import yaml

from src import reid
from src.config import DEFAULTS
from src.reid import ReIdSession

REPO_ROOT = Path(__file__).resolve().parents[1]

# Tài liệu SỐNG người đọc dùng để trình bày/báo cáo. KHÔNG gồm docs/task + docs/research
# vì đó là log lịch sử (AGENTS.md: không sửa log cũ) — chúng được phép ghi lại trạng thái cũ.
TAI_LIEU_SONG = (
    "README.md",
    "docs/tom-tat-do-an.md",
    "docs/demo-ngay-mai.md",
    "docs/giai-thich-do-an.md",
    "docs/cheatsheet-lenh.md",
)

# Ngưỡng re-ID: tên key trong config → (hằng số trong reid.py, thuộc tính trên ReIdSession)
BANG_NGUONG = {
    "reid_obj_threshold": (reid.DEFAULT_OBJ_THRESHOLD, "obj_threshold"),
    "reid_obj_min_side": (reid.DEFAULT_OBJ_MIN_SIDE, "obj_min_side"),
    "reid_obj_min_fill": (reid.DEFAULT_OBJ_MIN_FILL, "obj_min_fill"),
    "reid_obj_top_k": (reid.DEFAULT_OBJ_TOP_K, "obj_top_k"),
    "reid_obj_ncc_min": (reid.DEFAULT_OBJ_NCC_MIN, "obj_ncc_min"),
    "lost_score_threshold": (reid.DEFAULT_LOST_SCORE_THRESHOLD, "lost_score_threshold"),
    "reid_reacquire_confirm": (reid.DEFAULT_REACQUIRE_CONFIRM, "reacquire_confirm"),
    "reid_verify_frames": (reid.DEFAULT_VERIFY_FRAMES, "verify_frames"),
}


def _yaml_cfg() -> dict:
    with open(REPO_ROOT / "configs" / "default.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


class TestBonNguonKhopNhau:
    """DEFAULTS ↔ configs/default.yaml ↔ hằng số reid.py ↔ tham số ReIdSession."""

    def test_yaml_khop_defaults(self):
        cfg = _yaml_cfg()
        for key in BANG_NGUONG:
            assert key in cfg, f"configs/default.yaml thiếu key {key}"
            assert cfg[key] == DEFAULTS[key], f"{key}: yaml={cfg[key]} != DEFAULTS={DEFAULTS[key]}"

    def test_hang_so_reid_py_khop_defaults(self):
        for key, (hang_so, _attr) in BANG_NGUONG.items():
            assert hang_so == DEFAULTS[key], f"{key}: reid.py={hang_so} != DEFAULTS={DEFAULTS[key]}"

    def test_tham_so_session_khop_defaults(self):
        # Đây là ca bug 27-10: tham số __init__ ĐÈ hằng số → giá trị hiệu lực khác config.
        s = ReIdSession(engine=None, embedder=None, cue="object")
        for key, (_hang_so, attr) in BANG_NGUONG.items():
            assert getattr(s, attr) == DEFAULTS[key], \
                f"{key}: ReIdSession.{attr}={getattr(s, attr)} != DEFAULTS={DEFAULTS[key]}"


class TestTaiLieuKhongNoiSai:
    """Tài liệu phải trỏ về config, không được khẳng định 'bật mặc định' khi cấu hình đang TẮT."""

    def test_cong_ncc_dang_tat_thi_tai_lieu_khong_noi_bat_mac_dinh(self):
        assert DEFAULTS["reid_obj_ncc_min"] == 0.0, "test này chỉ đúng khi cổng NCC đang TẮT"
        for ten in TAI_LIEU_SONG:
            text = (REPO_ROOT / ten).read_text(encoding="utf-8")
            for m in re.finditer(r"cổng NCC[^\n]*bật mặc định", text, flags=re.IGNORECASE):
                raise AssertionError(
                    f"{ten}: tài liệu nói cổng NCC 'bật mặc định' nhưng cấu hình là 0.0 (TẮT) "
                    f"→ «{m.group(0).strip()}»")

    def test_khong_goi_y_nguong_ncc_070_nhu_gia_tri_dung(self):
        """0,70 là giá trị SAI: dữ liệu thật cho thấy nó chặn 6/17 ca đúng (min ncc = 0,415)."""
        for ten in TAI_LIEU_SONG:
            text = (REPO_ROOT / ten).read_text(encoding="utf-8")
            for m in re.finditer(r"(?:đặt|dùng|bật)\s+ngưỡng\s+(?:NCC\s+)?0[,.]70", text,
                                 flags=re.IGNORECASE):
                raise AssertionError(
                    f"{ten}: gợi ý đặt ngưỡng 0,70 là SAI (chặn 6/17 ca đúng) → «{m.group(0)}»")

    def test_cong_ncc_khong_duoc_goi_la_cong_chinh(self):
        """Cosine là cổng chính, NCC là cổng phụ (accept_candidate) — tài liệu phải nói đúng."""
        for ten in TAI_LIEU_SONG:
            text = (REPO_ROOT / ten).read_text(encoding="utf-8")
            for m in re.finditer(r"NCC[^\n]{0,20}cổng CHÍNH", text):
                raise AssertionError(f"{ten}: gọi NCC là 'cổng CHÍNH' là sai → «{m.group(0)}»")
