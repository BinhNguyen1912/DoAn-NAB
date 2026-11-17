"""Ảnh quỹ đạo cho báo cáo (`scripts/make_trajectory_media.py`).

Điều được ghim ở đây, vì đây là ảnh **dùng làm bằng chứng**:
- dòng KHÔNG có toạ độ (mask rỗng / hộp suy biến) **không** được biến thành toạ độ `0` — 0 là một vị
  trí thật trên khung, khác hẳn "không đo được" (AGENTS §6);
- CSV thiếu cột phải **báo lỗi**, không được vẽ ra ảnh trông hợp lệ từ dữ liệu rỗng;
- `--expect-bbox` lệch >10 % phải **cảnh báo** — bẫy thật 14-11: ô chọn phủ khuôn mặt thay vì chai,
  và mọi số của phase đó thành vô nghĩa.
"""

import numpy as np
import pytest

from scripts import make_trajectory_media as tm

HEADER = "frame_idx,seq,vos_ms,empty,drift_iou,bbox_x1,bbox_y1,bbox_x2,bbox_y2\n"


def _write(tmp_path, rows, header=HEADER):
    path = tmp_path / "drift.csv"
    path.write_text(header + "".join(row + "\n" for row in rows), encoding="utf-8")
    return path


class TestReadTraj:
    def test_doc_toa_do_hai_dong(self, tmp_path):
        path = _write(tmp_path, [
            "0,1,120.0,0,0.87,100,100,200,300",
            "3,2,130.0,0,0.85,110,105,215,310",
        ])
        traj = tm.read_traj(path)
        data = traj["data"]
        assert traj["n_dong"] == 2 and traj["n_thieu_toa_do"] == 0
        assert float(data["cx"][0]) == pytest.approx(150.0)
        assert float(data["cy"][1]) == pytest.approx(207.5)
        assert float(data["w"][0]) == pytest.approx(100.0)

    def test_dong_khong_co_toa_do_thanh_None_khong_phai_0(self, tmp_path):
        """Mask rỗng ⇒ VOS không có hộp. `0` sẽ vẽ một điểm ở góc khung — sai lệch hoàn toàn."""
        path = _write(tmp_path, [
            "0,1,120.0,1,0.0,,,,",
            "3,2,130.0,0,0.85,110,105,215,310",
        ])
        traj = tm.read_traj(path)
        assert traj["data"]["cx"][0] is None
        assert traj["n_thieu_toa_do"] == 1
        assert traj["n_dong"] == 2

    def test_hop_suy_bien_bi_coi_la_thieu_toa_do(self, tmp_path):
        """x2 <= x1 (hộp cao/rộng âm) từng vô hiệu hoá cả một phase đo — phải bị loại."""
        path = _write(tmp_path, ["0,1,120.0,0,0.5,200,300,100,100"])
        traj = tm.read_traj(path)
        assert traj["data"]["cx"][0] is None and traj["n_thieu_toa_do"] == 1

    def test_thieu_cot_thi_bao_loi(self, tmp_path):
        path = _write(tmp_path, ["0,1,120.0,0,0.5,100,100,200,300"],
                      header="frame_idx,seq,vos_ms,empty,drift_iou\n")
        with pytest.raises(ValueError, match="thiếu cột"):
            tm.read_traj(path)

    def test_csv_rong_khong_no(self, tmp_path):
        traj = tm.read_traj(_write(tmp_path, []))
        assert traj["n_dong"] == 0
        fig, thong_ke = tm.draw(traj)
        import matplotlib.pyplot as plt

        plt.close(fig)
        assert thong_ke["n_co_toa_do"] == 0


class TestDraw:
    def _traj(self, n=30, empty_at=()):
        rows = []
        for i in range(n):
            x1 = 100 + 5 * i
            rows.append(f"{i * 3},{i + 1},120.0,{1 if i in empty_at else 0},0.85,"
                        f"{x1},{100 + 2 * i},{x1 + 120},{340 + 3 * i}")
        return rows

    def test_ve_duoc_va_thong_ke_dung(self, tmp_path):
        import matplotlib.pyplot as plt

        traj = tm.read_traj(_write(tmp_path, self._traj()))
        fig, thong_ke = tm.draw(traj)
        plt.close(fig)
        assert thong_ke["n_co_toa_do"] == 30
        assert thong_ke["n_mask_rong"] == 0
        assert thong_ke["drift_n"] == 30
        assert thong_ke["drift_iou_p05"] == pytest.approx(0.85, abs=1e-6)

    def test_mat_dau_van_ve_duoc_va_duoc_dem(self, tmp_path):
        import matplotlib.pyplot as plt

        traj = tm.read_traj(_write(tmp_path, self._traj(empty_at=(5, 6))))
        fig, thong_ke = tm.draw(traj)
        plt.close(fig)
        assert thong_ke["n_mask_rong"] == 2

    def test_p05_None_khi_chua_du_mau(self, tmp_path):
        """`None` ≠ 0: 10 mẫu không đủ để nói phân vị 5 (AGENTS §6)."""
        import matplotlib.pyplot as plt

        traj = tm.read_traj(_write(tmp_path, self._traj(n=10)))
        fig, thong_ke = tm.draw(traj)
        plt.close(fig)
        assert thong_ke["drift_n"] == 10 and thong_ke["drift_iou_p05"] is None
        assert thong_ke["drift_iou_mean"] is not None

    def test_nguong_la_30_chung_voi_status_json_khong_phai_20(self, tmp_path):
        """Ticket #23: script này từng tự đặt ngưỡng **20** ⇒ 29 mẫu vẫn công bố `drift_iou_p05`.

        Cùng một đại lượng mà `status.json` từ chối công bố dưới 30 mẫu ⇒ hai con số p05 trong báo
        cáo không so được với nhau. 29 mẫu phải là `None`, 30 mẫu mới công bố.
        """
        import matplotlib.pyplot as plt

        from src import drift_samples as ds

        assert tm.MIN_SAMPLES == ds.MIN_SAMPLES
        traj = tm.read_traj(_write(tmp_path, self._traj(n=29)))
        fig, thong_ke = tm.draw(traj)
        plt.close(fig)
        assert thong_ke["drift_n"] == 29 and thong_ke["drift_iou_p05"] is None

    def test_anh_nen_sai_kich_thuoc_khong_lam_sap(self, tmp_path):
        import matplotlib.pyplot as plt

        traj = tm.read_traj(_write(tmp_path, self._traj()))
        fig, _ = tm.draw(traj, background=np.zeros((40, 60, 3), np.uint8))
        plt.close(fig)


class TestCanhBaoBbox:
    def _traj(self, tmp_path, bbox="288,287,431,734"):
        x1, y1, x2, y2 = (int(v) for v in bbox.split(","))
        return tm.read_traj(_write(tmp_path, [f"0,1,120.0,0,0.85,{x1},{y1},{x2},{y2}"]))

    def test_khop_thi_khong_canh_bao(self, tmp_path, capsys):
        """Hộp của CSV ≈ hộp mong đợi (lệch < 10 %) ⇒ không cảnh báo."""
        tm._canh_bao_bbox(self._traj(tmp_path, bbox="305,280,445,690"), "300,275,150,410")
        out = capsys.readouterr().out
        assert "khớp" in out and "CẢNH BÁO" not in out

    def test_xywh_suy_ra_duoc_khi_x2_nho_hon_x1(self, tmp_path, capsys):
        """`300,275,150,410` KHÔNG mơ hồ (x2=150 <= x1=300) ⇒ suy ra `(x,y,w,h)` và nói rõ đã suy ra."""
        kq = tm._canh_bao_bbox(self._traj(tmp_path, bbox="305,280,445,690"), "300,275,150,410")
        out = capsys.readouterr().out
        assert kq == "khop" and "SUY RA: xywh" in out

    def test_lech_nhieu_thi_canh_bao_to(self, tmp_path, capsys):
        """Ô phủ mặt (100,300 → 330,660) so với ô chọn đúng vật (300,275 → 450,685)."""
        tm._canh_bao_bbox(self._traj(tmp_path, bbox="100,300,330,660"), "300,275,150,410")
        out = capsys.readouterr().out
        assert "CẢNH BÁO" in out and "SAI VẬT" in out

    def test_expect_bbox_sai_dinh_dang_khong_no(self, tmp_path, capsys):
        assert tm._canh_bao_bbox(self._traj(tmp_path), "không-phải-số") == "khong_ket_luan"
        out = capsys.readouterr().out
        assert "KHÔNG KẾT LUẬN" in out and "expect-bbox-dang" in out

    # ── ticket #25: KHÔNG đoán dạng hộp ────────────────────────────────────────────────────────
    def test_hop_mo_ho_khong_ket_luan_thay_vi_doan(self, tmp_path, capsys):
        """`50,100,300,400` là `(x,y,w,h)` hợp lệ **và** cũng đọc được thành `(x1,y1,x2,y2)`.
        Bản cũ đoán `x1,y1,x2,y2` ⇒ có thể in "ô bao khớp" OAN (ticket #25)."""
        # CSV dòng đầu ĐÚNG BẰNG giá trị mơ hồ ⇒ code cũ (đoán `xyxy`) in "khớp" oan, còn code mới
        # phải nói "không so được". Đây là ca của ticket #25.
        kq = tm._canh_bao_bbox(self._traj(tmp_path, bbox="50,100,300,400"), "50,100,300,400")
        out = capsys.readouterr().out
        assert kq == "khong_ket_luan"
        assert "khớp" not in out and "CẢ hai kiểu" in out

    def test_khai_dang_xywh_thi_so_duoc_hop_mo_ho(self, tmp_path, capsys):
        """Khai `--expect-bbox-dang xywh` ⇒ `50,100,300,400` = hộp 300×400 tại (50,100)."""
        kq = tm._canh_bao_bbox(self._traj(tmp_path, bbox="50,100,350,500"),
                               "50,100,300,400", "xywh")
        assert kq == "khop" and "khớp" in capsys.readouterr().out

    def test_tien_to_xywh_trong_gia_tri_cung_duoc(self, tmp_path, capsys):
        kq = tm._canh_bao_bbox(self._traj(tmp_path, bbox="50,100,350,500"), "xywh:50,100,300,400")
        assert kq == "khop" and "khớp" in capsys.readouterr().out

    def test_tien_to_xyxy_voi_hop_sai_chieu_thi_bao_loi(self, tmp_path, capsys):
        """Khai `xyxy:` mà `y2 <= y1` ⇒ nói rõ phải khai `xywh`, không tự đổi hộ."""
        kq = tm._canh_bao_bbox(self._traj(tmp_path), "xyxy:50,100,300,40")
        assert kq == "khong_ket_luan" and "xywh" in capsys.readouterr().out

    def test_xyxy_hop_le_van_so_duoc(self, tmp_path, capsys):
        kq = tm._canh_bao_bbox(self._traj(tmp_path, bbox="305,280,445,690"), "xyxy:300,275,450,685")
        assert kq == "khop" and "khớp" in capsys.readouterr().out

    def test_nan_inf_bi_tu_choi(self, tmp_path, capsys):
        """`max()` bỏ qua NaN và `nan > 0.1` là False ⇒ nếu không chặn, cổng in "khớp" với hộp vô nghĩa
        (P1 review 16-11)."""
        for gia_tri in ("nan,100,300,400", "50,100,inf,400", "50,100,300,-inf"):
            for dang in ("xywh", "xyxy"):
                assert tm._canh_bao_bbox(self._traj(tmp_path), gia_tri, dang) == "khong_ket_luan"
        out = capsys.readouterr().out
        assert "không hữu hạn" in out and "khớp" not in out

    def test_csv_co_nan_khong_ket_luan(self, tmp_path, capsys):
        traj = tm.read_traj(_write(tmp_path, ["0,1,120.0,0,0.85,nan,nan,nan,nan"]))
        kq = tm._canh_bao_bbox(traj, "300,275,150,410")
        out = capsys.readouterr().out
        assert kq in ("khong_ket_luan", "lech"), out
        assert "khớp" not in out

    def test_csv_rong_khong_no(self, tmp_path, capsys):
        traj = tm.read_traj(_write(tmp_path, []))
        assert tm._canh_bao_bbox(traj, "300,275,150,410") == "khong_ket_luan"
        assert "không so được" in capsys.readouterr().out

    def test_cli_co_rong_van_phai_qua_cong(self, tmp_path):
        """`--expect-bbox ""` (biến shell rỗng) từng là falsy ⇒ **bỏ qua cổng**, exit 0 (P2 review)."""
        path = _write(tmp_path, ["0,1,120.0,0,0.85,288,287,431,734"])
        assert tm.main(["--csv", str(path), "--out", str(tmp_path / "a.png"),
                        "--expect-bbox", ""]) == 1

    def test_cli_exit_0_khi_khop(self, tmp_path):
        path = _write(tmp_path, ["0,1,120.0,0,0.85,288,287,431,734"])
        assert tm.main(["--csv", str(path), "--out", str(tmp_path / "a.png"),
                        "--expect-bbox", "288,287,431,734", "--expect-bbox-dang", "xyxy"]) == 0

    def test_provenance_ghi_ket_luan_cua_cong(self, tmp_path):
        """Câu "đừng dùng ảnh này làm bằng chứng" chỉ ở stdout thì file `.json` trông y hệt lần đạt
        ⇒ JSON phải ghi `ket_qua_hop`/`iou_bbox` (P2 review 16-11)."""
        import json as _json

        path = _write(tmp_path, ["0,1,120.0,0,0.85,100,300,330,660"])
        meta = tmp_path / "a.json"
        assert tm.main(["--csv", str(path), "--out", str(tmp_path / "a.png"),
                        "--meta", str(meta), "--expect-bbox", "300,275,150,410"]) == 1
        payload = _json.loads(meta.read_text(encoding="utf-8"))
        assert payload["ket_qua_hop"] == "lech" and payload["expect_bbox_dang"] == "xywh"
        assert payload["expect_bbox"] == "300,275,150,410"
        assert payload["iou_bbox"] is not None and payload["iou_bbox"] < tm.IOU_CUNG_VAT

    def test_cli_exit_1_khi_hop_lech(self, tmp_path):
        """Exit 0 mà ô bao lệch ⇒ script tự động coi là "đạt". Ảnh vẫn ghi nhưng mã thoát phải 1."""
        path = _write(tmp_path, ["0,1,120.0,0,0.85,100,300,330,660"])
        ma = tm.main(["--csv", str(path), "--out", str(tmp_path / "a.png"),
                      "--expect-bbox", "300,275,150,410"])
        assert ma == 1

    def test_cli_exit_1_khi_khong_ket_luan(self, tmp_path):
        path = _write(tmp_path, ["0,1,120.0,0,0.85,100,300,330,660"])
        ma = tm.main(["--csv", str(path), "--out", str(tmp_path / "a.png"),
                      "--expect-bbox", "50,100,300,400"])
        assert ma == 1


class TestProvenance:
    """Ảnh media PHẢI có provenance để người đọc kiểm lại nguồn (E16 của review sản phẩm 14-11:
    ảnh sinh từ CSV đo bằng **ô phủ khuôn mặt** trông y như ảnh đo bằng ô chọn đúng vật)."""

    def test_ghi_du_thong_tin_kiem_lai_duoc(self, tmp_path):
        csv_path = tmp_path / "drift.csv"
        csv_path.write_text("x", encoding="utf-8")
        clip = tmp_path / "clip.mp4"
        clip.write_bytes(b"video")
        out = tmp_path / "anh.png"
        out.write_bytes(b"png")

        meta = tm.provenance(csv_path, clip, out, "tiêu đề", (288, 287, 431, 734))
        assert meta["csv_sha256_16"] and meta["clip_sha256_16"] and meta["anh_sha256_16"]
        assert meta["bbox_dong_dau_x1y1x2y2"] == [288, 287, 431, 734]
        assert meta["git_rev"], "phải có git_rev để truy ảnh về đúng commit"
        assert "KHÔNG phải độ chính xác" in meta["canh_bao"]

    def test_thieu_clip_van_ghi_duoc(self, tmp_path):
        csv_path = tmp_path / "d.csv"
        csv_path.write_text("x", encoding="utf-8")
        meta = tm.provenance(csv_path, None, tmp_path / "a.png", "", None)
        assert meta["clip"] is None and meta["bbox_dong_dau_x1y1x2y2"] is None
        assert meta["git_rev"]

    def test_cli_ghi_json_canh_anh(self, tmp_path):
        import json as _json

        path = _write(tmp_path, ["0,1,120.0,0,0.85,288,287,431,734",
                                 "3,2,120.0,0,0.85,290,289,433,736"])
        out = tmp_path / "traj.png"
        meta = tmp_path / "traj.json"
        assert tm.main(["--csv", str(path), "--out", str(out), "--meta", str(meta)]) == 0
        payload = _json.loads(meta.read_text(encoding="utf-8"))
        assert payload["bbox_dong_dau_x1y1x2y2"] == [288, 287, 431, 734]
        assert payload["anh"].endswith("traj.png")
        # Ticket #23: số của ẢNH phải nằm trong file provenance — `drift_iou_p05 = None` chỉ đọc được
        # là "n < 30" khi `drift_n`/`drift_iou_p05_nguong` ở ngay cạnh, không phải đoán.
        thong_ke = payload["thong_ke"]
        assert thong_ke["drift_iou_p05_nguong"] == tm.MIN_SAMPLES
        assert thong_ke["drift_n"] == 2 and thong_ke["drift_iou_p05"] is None


class TestDirtyCode:
    """Bug thật 14-11: `.strip()` cả khối `git status` làm mất dấu cách đầu dòng ⇒ `docs/media/` không
    được miễn trừ ⇒ mọi ảnh media tự khai "cây bẩn"."""

    def test_dong_dau_co_dau_cach_van_duoc_mien_tru(self):
        assert tm._dirty_code(" M docs/media/traj/a.png\n M data/x.json\n") is False

    def test_code_ban_thi_true(self):
        assert tm._dirty_code(" M docs/media/a.png\n M src/live_tracking.py\n") is True

    def test_untracked_trong_data_va_media_duoc_mien_tru(self):
        assert tm._dirty_code("?? data/new.json\n?? docs/media/traj/b.json\n") is False

    def test_cay_sach(self):
        assert tm._dirty_code("") is False
        assert tm._dirty_code("\n") is False
