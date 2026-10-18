"""Test phần logic thuần của scripts/colab_run_all.py (không chạy model/không mạng)."""

import pytest

from types import SimpleNamespace

from scripts.colab_run_all import (
    CKPT_MIN_BYTES, checkpoint_ok, ensure_video, write_run_info, zip_results,
)


class TestCheckpointOk:
    def test_file_nho_hon_100mb_la_hong(self, tmp_path):
        p = tmp_path / "ckpt.pt"
        p.write_bytes(b"x" * 1000)
        assert checkpoint_ok(str(p)) is False        # file 0/ngắn byte từng làm hỏng phiên Colab

    def test_file_du_lon_la_ok(self, tmp_path):
        p = tmp_path / "ckpt.pt"
        with open(p, "wb") as f:
            f.seek(CKPT_MIN_BYTES)                    # sparse file, không tốn đĩa
            f.write(b"x")
        assert checkpoint_ok(str(p)) is True

    def test_khong_ton_tai(self, tmp_path):
        assert checkpoint_ok(str(tmp_path / "khong_co.pt")) is False


class TestEnsureVideo:
    def test_dung_video_co_san(self, tmp_path):
        v = tmp_path / "in.mp4"
        v.write_bytes(b"x" * 10)
        assert ensure_video(str(v)) == str(v)

    def test_khong_co_va_cam_sinh_thi_bao_loi(self, tmp_path):
        with pytest.raises(FileNotFoundError, match="upload"):
            ensure_video(str(tmp_path / "khong_co.mp4"), synthetic=False)

    def test_sinh_video_test_va_mo_lai_duoc(self, tmp_path):
        import cv2

        out = ensure_video(str(tmp_path / "auto.mp4"), synthetic=True, frames=4)
        cap = cv2.VideoCapture(out)
        assert cap.isOpened()
        assert int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) == 4
        cap.release()


class TestZipResults:
    def test_dong_goi_cac_file_ket_qua(self, tmp_path):
        (tmp_path / "out_gpu.mp4").write_bytes(b"v")
        (tmp_path / "gpu_metrics.csv").write_text("a,b\n1,2\n")
        (tmp_path / "gpu_summary.json").write_text("{}")
        (tmp_path / "khac.txt").write_text("bo qua")
        z = zip_results(str(tmp_path), str(tmp_path / "res.zip"), tag="gpu")
        import zipfile

        names = set(zipfile.ZipFile(z).namelist())
        assert names == {"out_gpu.mp4", "gpu_metrics.csv", "gpu_summary.json"}


class TestWriteRunInfo:
    def test_ghi_commit_va_tham_so(self, tmp_path):
        args = SimpleNamespace(device="cuda", image_size=512, reanchor_every=10,
                               bbox="200,200,120,120", video="data/input.mp4", max_frames=None)
        path = write_run_info("gpu", args, out_dir=str(tmp_path))
        import json

        info = json.load(open(path, encoding="utf-8"))
        assert info["tag"] == "gpu"
        assert info["git_rev"] and info["git_rev"] != "unknown"   # đang chạy trong repo git
        assert info["image_size"] == 512 and info["reanchor_every"] == 10
        assert info["video"] == "input.mp4"
