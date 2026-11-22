"""Test cho `scripts/paired_miou.py` — trọng tâm: sign test TÍNH ĐÚNG (bản nháp đầu quên chia 2^n)."""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.paired_miou import (  # noqa: E402
    bootstrap_ci,
    cap_frame,
    sign_test_hai_phia,
    so_sanh,
    tim_dong,
)


@pytest.mark.parametrize("k, n, p", [
    (8, 8, 0.0078),      # 2 * 1 / 256
    (0, 8, 0.0078),
    (7, 8, 0.0703),      # 2 * (C(8,7)+C(8,8)) / 256 = 18/256
    (6, 8, 0.2891),      # 2 * 37 / 256
    (4, 8, 1.0),         # đúng giữa ⇒ không có bằng chứng
    (5, 8, 0.7266),
])
def test_sign_test(k, n, p):
    assert sign_test_hai_phia(k, n) == pytest.approx(p, abs=5e-4)


def test_sign_test_n_rong():
    import math
    assert math.isnan(sign_test_hai_phia(0, 0))


def _art(size: int, ious: dict, *, schema_pairs=True):
    frames = [[i, v] for i, v in ious.items()] if schema_pairs else \
             [{"frame_idx": i, "iou": v} for i, v in ious.items()]
    return {"ket_qua": [{"image_size": size, "ms_moi_frame": 100.0,
                         "chi_tiet": {"binh2_tay": {"n_cham": len(ious), "frames": frames}}}]}


def test_tim_dong_bao_loi_khi_thieu():
    with pytest.raises(SystemExit):
        tim_dong(_art(192, {}), 320)


def test_tim_dong_bao_loi_khi_dong_loi():
    a = {"ket_qua": [{"image_size": 512, "ma_thoat": 1, "status_message": "nổ"}]}
    with pytest.raises(SystemExit, match="LỖI"):
        tim_dong(a, 512)


def test_cap_frame_chi_lay_frame_chung_va_bo_gt_rong():
    a = {"image_size": 192, "chi_tiet": {"binh2_tay": {"frames": [[0, 0.5], [1, None], [2, 0.6]]}}}
    b = {"image_size": 320, "chi_tiet": {"binh2_tay": {"frames": [[0, 0.7], [2, 0.65], [3, 0.9]]}}}
    assert cap_frame(a, b, "binh2_tay") == [(0, 0.5, 0.7), (2, 0.6, 0.65)]


def test_doc_duoc_ca_hai_luoc_do():
    """`schema 1` ghi cặp `[idx, iou]`, `schema 2` ghi dict — công cụ phải đọc được cả hai."""
    a = tim_dong(_art(192, {0: 0.5}, schema_pairs=True), 192)
    b = tim_dong(_art(320, {0: 0.8}, schema_pairs=False), 320)
    assert cap_frame(a, b, "binh2_tay") == [(0, 0.5, 0.8)]


def test_so_sanh_dung_dau_va_ci():
    a = tim_dong(_art(192, {0: 0.50, 1: 0.50, 2: 0.50, 3: 0.50}), 192)
    b = tim_dong(_art(320, {0: 0.90, 1: 0.90, 2: 0.90, 3: 0.90}), 320)
    r = so_sanh(a, b, "binh2_tay")
    assert r["n"] == 4 and r["so_duong"] == 4
    assert r["mean"] == pytest.approx(0.4)
    assert r["ci95"][0] > 0            # 4/4 đều tăng ⇒ CI không bắc qua 0
    assert r["p_sign"] == pytest.approx(0.125)   # 2 * 1 / 16


def test_bootstrap_ci_khi_moi_chenh_lech_bang_0():
    lo, hi = bootstrap_ci([0.0, 0.0, 0.0])
    assert lo == pytest.approx(0.0) and hi == pytest.approx(0.0)


def test_chay_end_to_end(tmp_path):
    da = tmp_path / "a.json"
    db = tmp_path / "b.json"
    da.write_text(json.dumps(_art(192, {0: 0.5, 1: 0.6})), encoding="utf-8")
    db.write_text(json.dumps(_art(320, {0: 0.8, 1: 0.9})), encoding="utf-8")
    from scripts.paired_miou import main
    assert main(["--a", str(da), "--b", str(db), "--size-a", "192", "--size-b", "320"]) == 0
