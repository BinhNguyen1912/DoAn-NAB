"""Khoá MẶC ĐỊNH ô chọn của các script đo — để không tái diễn lỗi "ô nằm trên khuôn mặt".

Bối cảnh: ngày 14-11 phát hiện `binh1.mp4` = 720×1280 và ô `104,308,209,287` phủ **khuôn mặt**
người (chai nằm ngoài hộp), còn `binh2.mp4` ô `200,400,300,500` phủ **2 chai + 2 bàn tay**. Ba script
dưới đây để mặc định ô đó ⇒ mọi phép đo "mới" lại rơi vào lỗi cũ (21 artifact đã bị ảnh hưởng).
Nguồn sự thật về ô + khung frame: `docs/demo-clip-va-o-chon.md`.

Test này KHÔNG kiểm tra "ô có đúng vật hay không" (phải xem ảnh — xem `docs/media/bbox/`); nó chỉ khoá
việc **mặc định mới bằng mặc định đã được audit bằng ảnh**, và khoá việc ô cũ (trên mặt) không quay lại.
"""

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
# Ô chai của data/binh1.mp4, chốt bằng ảnh frame 0 (docs/media/bbox/binh1_bbox_moi_300-275-150-410.jpg).
O_CHAI_BINH1 = "300,275,150,410"
# Ô CŨ — phủ KHUÔN MẶT, đã bị đình chỉ 14-11.
O_MAT_SAI = "104,308,209,287"

SCRIPTS = [
    "scripts/profile_stages.py",
    "scripts/benchmark_light_trackers.py",
    "scripts/measure_watchdog.py",
]
# `profile_stages.py` parse `x1,y1,x2,y2` (KHÔNG phải x,y,w,h) — đổi nhầm định dạng ở đây từng tạo ra
# ô có `x2 < x1` (rộng âm) mà test cũ vẫn xanh. Xem `test_o_chon_khong_bi_suy_bien`.
DINH_DANG = {
    "scripts/profile_stages.py": "xyxy",
    "scripts/benchmark_light_trackers.py": "xywh",
    "scripts/measure_watchdog.py": "xywh",
}
O_CHAI_BINH1_XYXY = "300,275,450,685"   # 300,275 + 150×410


def _default_bbox(path: str) -> str:
    """Đọc `--bbox` mặc định của một script (argparse: `add_argument("--bbox", default="...")`)."""
    text = (REPO_ROOT / path).read_text(encoding="utf-8")
    match = re.search(r'add_argument\(\s*"--bbox"\s*,\s*default\s*=\s*"([^"]+)"', text)
    assert match, f"{path} không còn `--bbox` với default dạng chuỗi literal"
    return match.group(1)


@pytest.mark.parametrize("path", SCRIPTS)
def test_mac_dinh_bbox_la_o_chai_khong_phai_o_mat(path):
    """Mỗi script phải mặc định ô CHAI, ĐÚNG ĐỊNH DẠNG của chính nó."""
    ky_vong = O_CHAI_BINH1_XYXY if DINH_DANG[path] == "xyxy" else O_CHAI_BINH1
    assert _default_bbox(path) == ky_vong, (
        f"{path}: mặc định `--bbox` phải là {ky_vong} (định dạng {DINH_DANG[path]}), "
        f"ô {O_MAT_SAI} phủ khuôn mặt — xem docs/demo-clip-va-o-chon.md"
    )


@pytest.mark.parametrize("path", SCRIPTS)
def test_o_chon_khong_bi_suy_bien(path):
    """Ô mặc định phải có chiều rộng/cao DƯƠNG — bắt được lỗi trộn `xywh` vào script parse `xyxy`.

    Lỗi thật 14-11 (review độc lập bắt): đặt mặc định `300,275,150,410` cho `profile_stages.py` (script
    parse `x1,y1,x2,y2`) ⇒ hộp `(300,275)-(150,410)` tức `x2 < x1`, rộng **âm**; test khoá-chuỗi cũ
    vẫn xanh nên không ai thấy (AGENTS §6: "hộp cao âm" từng làm hỏng cả một pha đo).
    """
    x1, y1, x2, y2 = (int(v) for v in _default_bbox(path).split(","))
    if DINH_DANG[path] == "xyxy":
        assert x2 > x1 and y2 > y1, f"{path}: hộp suy biến ({x1},{y1})-({x2},{y2})"
        assert (x2 - x1, y2 - y1) == (150, 410), f"{path}: kích thước phải là 150×410"
    else:
        assert x2 > 0 and y2 > 0, f"{path}: w/h phải dương, đang là {x2}×{y2}"
        assert (x2, y2) == (150, 410), f"{path}: kích thước phải là 150×410"


@pytest.mark.parametrize("path", SCRIPTS)
def test_khong_con_mac_dinh_o_mat(path):
    """Khoá hồi quy: đổi lại thành ô mặt (hoặc thêm script mới copy bản cũ) là đỏ ngay."""
    assert _default_bbox(path) != O_MAT_SAI


def test_measure_live_relay_bat_buoc_truyen_bbox():
    """`measure_live_relay.py` phải để `--bbox` RỖNG mặc định (người chạy buộc phải chỉ định ô).

    Docstring của nó đã ghi rõ: `ket_qua = true` chỉ nói "đường ống chạy được", bbox sai thì số
    `drift_iou` vô nghĩa (13-11: bbox trỏ nền vẫn `ket_qua = true`). Có mặc định là ô nào đó ⇒ người
    chạy quên `--bbox` sẽ đo vào ô của clip KHÁC mà không biết.
    """
    text = (REPO_ROOT / "scripts/measure_live_relay.py").read_text(encoding="utf-8")
    match = re.search(r'add_argument\(\s*"--bbox"\s*,\s*default\s*=\s*"([^"]*)"', text)
    assert match, "không tìm thấy khai báo --bbox dạng literal trong measure_live_relay.py"
    assert match.group(1) == "", (
        "`--bbox` của measure_live_relay.py phải mặc định RỖNG (buộc người chạy tự chọn ô), "
        f"đang là {match.group(1)!r}"
    )
