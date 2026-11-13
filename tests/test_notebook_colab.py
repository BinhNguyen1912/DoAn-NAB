"""Test cấu trúc notebook Colab — không cần Colab, không cần model (làn nhanh).

Vì sao có: `notebooks/` không được test nào chạm tới ⇒ đổi tên biến / xoá cell sẽ không ai bắt, và
mục 8 từng để lọt lỗi thật ngày 13-11 (glob `data/live_*_metrics.json` nhặt cả artifact CPU đã commit
sẵn trong repo ⇒ in lẫn số CPU vào bảng GPU).
"""

import json
from pathlib import Path

NOTEBOOK = Path(__file__).resolve().parents[1] / "notebooks" / "colab_gpu_evaluation.ipynb"


def _cells():
    return json.loads(NOTEBOOK.read_text(encoding="utf-8"))["cells"]


def _source(cell):
    return "".join(cell.get("source", []))


def test_notebook_la_json_hop_le_va_co_cell_do_live():
    assert NOTEBOOK.exists()
    assert any(cell.get("cell_type") == "code" for cell in _cells())
    assert any("measure_live_relay" in _source(cell) for cell in _cells()), \
        "mục 8 (đo đường live trên GPU) biến mất khỏi notebook"


def test_muc_8_kiem_clip_va_bbox_truoc_khi_do():
    """Cell 8a phải kiểm video + bbox (bài học 13-11: bbox trỏ nền vẫn cho `ket_qua = true`)."""
    cells = _cells()
    kiem = [cell for cell in cells if "bbox_check.jpg" in _source(cell)]
    assert kiem, "cell 8a mất bước ghi data/bbox_check.jpg"
    source = _source(kiem[0])
    for manh in ("assert CHO_PHEP_CLIP_TONG_HOP", "la_clip_tong_hop", "n > 0", "n >= 30",
                 "0 <= x", "bw > 0", "da_ghi", "DA_KIEM_8A"):
        assert manh in source, f"cell 8a thiếu bước kiểm: {manh}"


def test_bien_khai_bao_truoc_khi_dung():
    """`VIDEO`/`BBOX`/`LAN` phải được định nghĩa ở cell TRƯỚC cell dùng (chạy từ trên xuống)."""
    cells = _cells()
    dinh_nghia = next(i for i, cell in enumerate(cells) if "LAN = (" in _source(cell))
    # 8b phải đòi cờ do 8a đặt (Colab "Run all" không được bỏ qua bước kiểm)
    assert "DA_KIEM_8A = True" in _source(cells[dinh_nghia]), "8a không đặt cờ DA_KIEM_8A"
    su_dung = next(i for i, cell in enumerate(cells)
                   if "for lan in LAN" in _source(cell))
    assert dinh_nghia < su_dung


def test_glob_cua_cell_in_so_chi_lay_file_do_cell_8b_sinh():
    """Glob rộng `live_*_metrics.json` nhặt cả artifact CPU đã commit ⇒ phải có `_lan`."""
    cells = _cells()
    in_so = [cell for cell in cells
             if "files.download" in _source(cell) and "8c)" in _source(cell)]
    assert in_so, "mất cell in số của mục 8"
    source = _source(in_so[0])
    assert "live_*_lan*_metrics.json" in source
    assert 'glob.glob("data/live_*_metrics.json")' not in source
    assert "assert paths" in source, "8c phải báo lỗi khi 8b không sinh được artifact nào"
    # Bảng số phải tự khai nguồn/bbox + `*_n` (tránh trích `0/None` như "đã đo")
    for manh in ("nguon", "bbox_xywh", "drift_n", "age_n", "stability_shown"):
        assert manh in source, f"cell in số thiếu: {manh}"


def test_glob_cua_8c_khong_khop_artifact_cpu_dang_co():
    """So pattern với TÊN FILE THẬT trong `data/` (không chỉ so chuỗi) — chặn va chạm trong tương lai.

    Reviewer PR #20 chỉ ra: so chuỗi thì biến thể `glob(...lan...) + glob(...*)` vẫn xanh. Test này
    kiểm bằng `fnmatch` trên mọi `data/live_*_metrics.json` đang có (artifact CPU đã commit sẵn).
    """
    import fnmatch
    import re

    cells = _cells()
    in_so = [cell for cell in cells if "files.download" in _source(cell) and "8c)" in _source(cell)]
    patterns = re.findall(r'glob\.glob\("data/([^"]+)"\)', _source(in_so[0]))
    assert patterns, "không tìm thấy pattern glob nào ở cell 8c"

    data = NOTEBOOK.parents[1] / "data"
    ung_vien = [p.name for p in data.glob("live_*_metrics.json")]
    assert ung_vien, "không có artifact live_*_metrics.json nào để kiểm (dấu hiệu repo thiếu data/)"
    for pattern in patterns:
        khop = [name for name in ung_vien if fnmatch.fnmatch(name, pattern)]
        assert not khop, f"pattern {pattern!r} nhặt cả artifact cũ: {khop[:3]}"
