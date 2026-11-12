"""Test phần logic thuần của scripts/colab_run_all.py (không chạy model/không mạng)."""

import os

import pytest

from types import SimpleNamespace

from scripts.colab_run_all import (
    CKPT_MIN_BYTES, checkpoint_ok, ensure_checkpoint, ensure_video, write_run_info, zip_results,
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


class TestEnsureCheckpoint:
    """Lỗi thật trên Colab 12-11: `dl.fbaipublicfiles.com` trả `certificate has expired` ⇒ cell
    "⚡ CHẠY TẤT CẢ" chết vì chỉ có MỘT URL và một cách TLS."""

    def _ghi(self, size):
        def fetch(url, path, context):
            with open(path, "wb") as handle:
                handle.write(b"x" * size)
        return fetch

    def test_nguon_dau_loi_thi_thu_nguon_sau(self, tmp_path):
        path = str(tmp_path / "ckpt.pt")
        da_goi = []
        ghi = self._ghi(50)

        def fetch(url, target, context):
            da_goi.append(url)
            if "fbaipublicfiles" in url:
                raise OSError("SSL: CERTIFICATE_VERIFY_FAILED")
            ghi(url, target, context)

        ensure_checkpoint(path, ("https://dl.fbaipublicfiles.com/x.pt", "https://huggingface.co/y.pt"),
                          min_bytes=10, fetch=fetch)
        assert os.path.getsize(path) == 50
        assert len(da_goi) >= 2, "phải thử nguồn dự phòng sau khi nguồn đầu lỗi"
        assert "huggingface" in da_goi[-1]

    def test_moi_nguon_loi_thi_bao_ro_da_thu_gi(self, tmp_path):
        def fetch(url, path, context):
            raise OSError("certificate has expired")

        with pytest.raises(RuntimeError) as info:
            ensure_checkpoint(str(tmp_path / "ckpt.pt"), ("https://huggingface.co/y.pt",),
                              min_bytes=10, fetch=fetch)
        message = str(info.value)
        assert "huggingface" in message and "certificate has expired" in message
        # Không để lại rác: không có file .part nào sót lại sau khi mọi cách thất bại.
        assert not list(tmp_path.glob("*.part"))

    def test_file_tai_ve_qua_nho_la_hong(self, tmp_path):
        with pytest.raises(RuntimeError, match="hỏng"):
            ensure_checkpoint(str(tmp_path / "nho.pt"), ("https://x/y.pt",), min_bytes=10,
                              fetch=self._ghi(5))

    def test_da_co_checkpoint_thi_khong_tai(self, tmp_path):
        path = tmp_path / "co.pt"
        path.write_bytes(b"x" * 50)

        def fetch(*_a, **_k):
            raise AssertionError("không được tải lại khi checkpoint đã đủ lớn")

        ensure_checkpoint(str(path), min_bytes=10, fetch=fetch)

    def test_ngu_canh_tls_cuoi_cung_la_bo_kiem_chung(self):
        """Nấc cuối phải là "bỏ kiểm chứng" — nó tồn tại vì CA store của Colab có thể lệch."""
        import ssl

        from scripts.colab_run_all import _ssl_contexts

        nhan = [ten for ten, _ctx in _ssl_contexts()]
        assert nhan[-1].startswith("KHÔNG")
        assert _ssl_contexts()[-1][1].verify_mode == ssl.CERT_NONE


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
