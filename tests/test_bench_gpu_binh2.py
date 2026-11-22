"""Test cho `scripts/bench_gpu_binh2.py` — tập trung vào các lỗi ĐÃ XẢY RA (review 22-11).

Không chạy model, không cần checkpoint: chỉ kiểm các hàm thuần (gộp artifact, đọc artifact cũ, suy ô
chọn, kiểm `image_size` hiệu lực, đọc số frame clip).
"""

import json
import sys
from pathlib import Path

import cv2
import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.bench_gpu_binh2 import (  # noqa: E402
    LoiBench,
    _doc_artifact_cu,
    _kiem_image_size,
    _o_chon_tu_gt,
    _so_frame_cua_clip,
    gop_ket_qua,
    tao_payload,
)

META = {"clip": "data/binh2.mp4", "o_chon_xywh": [1, 2, 3, 4], "vos_every": 1,
        "frames_gt": [0, 10], "gt_dirs": ["binh2_tay"], "git_rev": "abc123"}


def _art(rows, **ghi_de):
    return {"ket_qua": rows, **META, **ghi_de}


# ── P0: gộp phải GIỮ dòng của đợt trước ────────────────────────────────────────────────────────────
def test_gop_giu_dong_cu():
    cu = _art([{"image_size": 192, "mIoU": {"a": 0.76}}])
    moi = [{"image_size": 512, "mIoU": {"a": 0.83}}]
    ra = gop_ket_qua(cu, moi, META)
    assert [r["image_size"] for r in ra] == [192, 512]


def test_gop_dot_sau_thang_khi_trung():
    cu = _art([{"image_size": 192, "mIoU": {"a": 0.70}}])
    ra = gop_ket_qua(cu, [{"image_size": 192, "mIoU": {"a": 0.80}}], META)
    assert len(ra) == 1 and ra[0]["mIoU"]["a"] == 0.80


def test_gop_tu_choi_khac_o_chon():
    cu = _art([{"image_size": 192}], o_chon_xywh=[9, 9, 9, 9])
    with pytest.raises(LoiBench, match="o_chon_xywh"):
        gop_ket_qua(cu, [{"image_size": 512}], META)


def test_gop_tu_choi_khac_git_rev():
    cu = _art([{"image_size": 192}], git_rev="deadbee")
    with pytest.raises(LoiBench, match="git_rev"):
        gop_ket_qua(cu, [{"image_size": 512}], META)


def test_gop_khi_chua_co_artifact():
    ra = gop_ket_qua(None, [{"image_size": 320}, {"image_size": 192}], META)
    assert [r["image_size"] for r in ra] == [192, 320]


# ── P0: payload phải mang ĐÚNG list đã gộp (bug gán `rows` trước khi gộp) ─────────────────────────
def test_payload_mang_list_da_gop():
    cu = _art([{"image_size": 192}])
    rows = gop_ket_qua(cu, [{"image_size": 1024}], META)
    payload = tao_payload(rows=rows, meta=META, provenance={"git_rev": "abc123"},
                          lenh="x", max_frames=None, gt_dirs=["docs/gt/binh2_tay"])
    assert [r["image_size"] for r in payload["ket_qua"]] == [192, 1024]
    # và gán lại `rows` sau đó KHÔNG được đổi nội dung payload
    rows = []
    assert [r["image_size"] for r in payload["ket_qua"]] == [192, 1024]


# ── P2: artifact cũ hỏng cấu trúc phải NÉM, không được lặng lẽ ghi đè ────────────────────────────
@pytest.mark.parametrize("noi_dung", ["[]", "null", '{"ket_qua": "abc"}', '{"ket_qua": [1, 2]}', "{{"])
def test_doc_artifact_cu_hong(tmp_path, noi_dung):
    p = tmp_path / "a.json"
    p.write_text(noi_dung, encoding="utf-8")
    with pytest.raises(LoiBench):
        _doc_artifact_cu(p)


def test_doc_artifact_cu_chua_co(tmp_path):
    assert _doc_artifact_cu(tmp_path / "khong-co.json") is None


# ── P0: không đọc được số frame ⇒ KHÔNG được bỏ `--stop-after-frames` ────────────────────────────
def test_so_frame_clip_khong_mo_duoc(tmp_path):
    with pytest.raises(LoiBench, match="không mở được clip"):
        _so_frame_cua_clip(tmp_path / "khong-co.mp4")


def test_so_frame_clip_hong_bao_0(tmp_path, monkeypatch):
    """File rác: cv2 mở được nhưng `FRAME_COUNT` = 0 ⇒ phải NÉM (trước đây lặng lẽ bỏ cờ ⇒ lặp vô hạn)."""
    p = tmp_path / "rac.mp4"
    p.write_bytes(b"khong-phai-video")
    with pytest.raises(LoiBench):
        _so_frame_cua_clip(p)


def test_so_frame_clip_that(tmp_path):
    p = tmp_path / "ok.avi"
    w = cv2.VideoWriter(str(p), cv2.VideoWriter_fourcc(*"MJPG"), 5.0, (32, 24))
    for _ in range(7):
        w.write(np.zeros((24, 32, 3), np.uint8))
    w.release()
    if not p.is_file() or p.stat().st_size == 0:
        pytest.skip("không ghi được video bằng codec MJPG trên máy này")
    assert _so_frame_cua_clip(p) >= 7


# ── P1: `image_size` hiệu lực phải ĐÚNG ──────────────────────────────────────────────────────────
@pytest.mark.parametrize("ch, ly_do", [
    ({"image_size_kiem_duoc": True, "image_size_hieu_luc": 512}, None),
    ({"image_size_hieu_luc": 512}, None),
    ({"image_size_kiem_duoc": True, "image_size_hieu_luc": 1024}, "hiệu lực"),
    ({"image_size_kiem_duoc": False, "image_size_hieu_luc": 512, "cau_hinh_lech": ["x"]},
     "CHƯA KIỂM"),
    ({"image_size_hieu_luc": None}, "chưa kiểm"),
    ({}, "chưa kiểm"),
])
def test_kiem_image_size(ch, ly_do):
    ra = _kiem_image_size({"cau_hinh": ch}, 512)
    if ly_do is None:
        assert ra is None
    else:
        assert ra is not None and ly_do in ra


# ── P2: ô chọn suy từ FRAME ĐẦU TIÊN có trong index ─────────────────────────────────────────────
def _gt_dir(tmp_path, frames, size=(40, 30)):
    d = tmp_path / "gt"
    d.mkdir()
    items = []
    for idx, co_vat in frames:
        m = np.zeros(size[::-1], np.uint8)
        if co_vat:
            m[5:15, 10:25] = 1
        cv2.imwrite(str(d / f"gt_{idx:06d}.png"), m)
        items.append({"frame_idx": idx})
    (d / "index.json").write_text(json.dumps({"clip": "x", "frames": items}), encoding="utf-8")
    return d


def test_o_chon_dung_frame_dau_trong_index(tmp_path):
    d = _gt_dir(tmp_path, [(170, True), (180, True)])
    x, y, w, h = _o_chon_tu_gt(d)          # trước đây cứng gt_000000.png ⇒ ValueError
    assert (w, h) == (14, 9) and (x, y) == (10, 5)


def test_o_chon_bo_qua_frame_gt_rong(tmp_path):
    d = _gt_dir(tmp_path, [(0, False), (30, True)])
    assert _o_chon_tu_gt(d) == (10, 5, 14, 9)


def test_o_chon_khong_co_vat_nao(tmp_path):
    d = _gt_dir(tmp_path, [(0, False)])
    with pytest.raises(LoiBench):
        _o_chon_tu_gt(d)
