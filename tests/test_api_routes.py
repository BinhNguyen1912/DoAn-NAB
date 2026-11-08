"""Test tầng HTTP — chỉ kiểm tra ánh xạ request/response và mã lỗi, không kiểm lại nghiệp vụ.

Service được tiêm bằng adapter giả (xem `tests/conftest.py`) nên không cần model SAM 2,
không chạy subprocess, không cần video thật.
"""

import json

import numpy as np
import pytest

BOX = {"bbox": {"x": 2, "y": 2, "w": 20, "h": 16}}


@pytest.fixture
def client(service, api_settings):
    """TestClient dựng qua create_app (application factory) với service giả."""
    from fastapi.testclient import TestClient

    from src.api.main import create_app

    return TestClient(create_app(settings=api_settings, service=service))


def _upload(client, content=b"video-gia", name="v.mp4", **form):
    return client.post(
        "/api/jobs", files={"file": (name, content, "video/mp4")}, data=form
    )


class TestHealth:
    def test_health_tra_ok(self, client):
        r = client.get("/health")
        assert r.status_code == 200
        assert r.json() == {"status": "ok", "version": "0.1.0"}


class TestUpload:
    def test_upload_hop_le_tra_201(self, client, fs_store):
        r = _upload(client, image_size="256", reid="false")

        assert r.status_code == 201
        body = r.json()
        assert body["state"] == "uploaded"
        job = fs_store.get(body["job_id"])
        assert job is not None
        assert job.params["image_size"] == 256
        assert job.params["reid"] is False
        assert job.params["cue"] == "object"      # mặc định của web là bám VẬT

    def test_upload_sai_duoi_tra_400(self, client):
        r = _upload(client, content=b"khong-phai-video", name="tailieu.txt")
        assert r.status_code == 400
        assert "định dạng" in r.json()["detail"]

    def test_upload_cue_la_tra_422_tu_hop_dong(self, client):
        """`cue` là Literal trong hợp đồng → FastAPI từ chối ngay ở tầng validate."""
        assert _upload(client, cue="lung-tung").status_code == 422

    def test_upload_vuot_gioi_han_tra_413(self, client, api_settings):
        r = _upload(client, content=b"x" * (api_settings.max_upload_bytes + 10))
        assert r.status_code == 413

    def test_image_size_ngoai_khoang_tra_422(self, client):
        """Validate biên của Pydantic (hợp đồng API) — không phải nghiệp vụ."""
        assert _upload(client, image_size="9999").status_code == 422


class TestGetVaLietKe:
    def test_lay_job_dung_shape_hop_dong(self, client):
        job_id = _upload(client).json()["job_id"]

        body = client.get(f"/api/jobs/{job_id}").json()
        assert set(body) == {
            "job_id", "state", "progress", "message", "created_at",
            "bbox", "artifacts", "summary",
        }
        assert body["state"] == "uploaded"
        assert body["summary"] is None

    @pytest.mark.parametrize("job_id", [
        "20260101-000000-abcdef",     # đúng định dạng nhưng không tồn tại
        "khong-hop-le",               # sai định dạng
        "..%2F..%2Fetc%2Fpasswd",     # thử path traversal
    ])
    def test_job_khong_hop_le_tra_404(self, client, job_id):
        assert client.get(f"/api/jobs/{job_id}").status_code == 404

    def test_danh_sach_job(self, client):
        job_id = _upload(client).json()["job_id"]
        items = client.get("/api/jobs").json()
        assert [item["job_id"] for item in items] == [job_id]
        assert "summary" not in items[0]          # danh sách không kèm summary


def _client_with(settings, store, runner, probe):
    """Dựng TestClient với adapter tuỳ chọn — không đụng thuộc tính private của service."""
    from fastapi.testclient import TestClient

    from src.api.main import create_app
    from src.api.service import JobService

    service = JobService(store, runner, probe, settings)
    return TestClient(create_app(settings=settings, service=service))


class TestPreview:
    def test_preview_tra_jpeg_tu_probe(self, client):
        job_id = _upload(client).json()["job_id"]
        r = client.get(f"/api/jobs/{job_id}/preview")
        assert r.status_code == 200
        assert r.headers["content-type"] == "image/jpeg"
        assert r.content[:2] == b"\xff\xd8"

    def test_preview_that_bang_open_cv(self, api_settings, fs_store, fake_runner, write_video,
                                       tmp_path):
        """Kiểm adapter THẬT (Cv2VideoProbe) trên video có thật — chỉ 1 test để không chậm."""
        from src.api.adapters import Cv2VideoProbe

        real = _client_with(api_settings, fs_store, fake_runner, Cv2VideoProbe())
        frames = np.full((3, 48, 64, 3), 120, np.uint8)
        video = write_video(tmp_path / "v.mp4", frames, fps=10)
        job_id = _upload(real, content=video.read_bytes()).json()["job_id"]

        r = real.get(f"/api/jobs/{job_id}/preview")
        assert r.status_code == 200
        assert r.content[:2] == b"\xff\xd8"

    def test_preview_khong_doc_duoc_frame_tra_404(self, api_settings, fs_store, fake_runner,
                                                  make_probe):
        blind = _client_with(api_settings, fs_store, fake_runner, make_probe(jpeg=None))
        job_id = _upload(blind).json()["job_id"]
        assert blind.get(f"/api/jobs/{job_id}/preview").status_code == 404


class TestSelect:
    def test_select_hop_le_tra_202_va_khoi_chay(self, client, fake_runner):
        job_id = _upload(client).json()["job_id"]
        r = client.post(f"/api/jobs/{job_id}/select", json=BOX)

        assert r.status_code == 202
        assert r.json() == {"job_id": job_id, "state": "queued"}
        assert [call[0] for call in fake_runner.started] == [job_id]

    def test_bbox_rong_tra_422_tu_pydantic(self, client):
        job_id = _upload(client).json()["job_id"]
        r = client.post(f"/api/jobs/{job_id}/select", json={"bbox": {"x": 0, "y": 0, "w": 0, "h": 10}})
        assert r.status_code == 422

    def test_bbox_vuot_khung_tra_400_tu_loi_mien(self, client, fake_probe):
        fake_probe.size = (64, 48)
        job_id = _upload(client).json()["job_id"]
        r = client.post(f"/api/jobs/{job_id}/select",
                        json={"bbox": {"x": 60, "y": 0, "w": 20, "h": 10}})
        assert r.status_code == 400
        assert "64x48" in r.json()["detail"]

    def test_select_lan_hai_tra_409(self, client, fake_runner):
        job_id = _upload(client).json()["job_id"]
        assert client.post(f"/api/jobs/{job_id}/select", json=BOX).status_code == 202
        assert client.post(f"/api/jobs/{job_id}/select", json=BOX).status_code == 409


class TestArtifacts:
    def test_tai_artifact_da_co(self, client, fs_store):
        job_id = _upload(client).json()["job_id"]
        (fs_store.path(job_id) / "out.mp4").write_bytes(b"\x00\x00\x00\x18ftypmp42")

        r = client.get(f"/api/jobs/{job_id}/artifacts/out.mp4")
        assert r.status_code == 200
        assert r.content.startswith(b"\x00\x00\x00\x18ftyp")

    @pytest.mark.parametrize("name", ["job.json", "bi-mat.txt", "..%2Fjob.json"])
    def test_artifact_ngoai_whitelist_tra_404(self, client, fs_store, name):
        job_id = _upload(client).json()["job_id"]
        (fs_store.path(job_id) / "job.json").write_text("{}", encoding="utf-8")
        assert client.get(f"/api/jobs/{job_id}/artifacts/{name}").status_code == 404


class TestDelete:
    def test_xoa_tra_204_roi_khong_con(self, client):
        job_id = _upload(client).json()["job_id"]
        assert client.delete(f"/api/jobs/{job_id}").status_code == 204
        assert client.get(f"/api/jobs/{job_id}").status_code == 404

    def test_xoa_job_dang_chay_tra_409(self, client, fake_runner):
        job_id = _upload(client).json()["job_id"]
        client.post(f"/api/jobs/{job_id}/select", json=BOX)
        assert client.delete(f"/api/jobs/{job_id}").status_code == 409


class TestHopDongOpenApi:
    def test_schema_sinh_ra_co_du_endpoint(self, client):
        paths = client.get("/openapi.json").json()["paths"]
        assert set(paths) == {
            "/health",
            "/api/jobs",
            "/api/jobs/{job_id}",
            "/api/jobs/{job_id}/preview",
            "/api/jobs/{job_id}/select",
            "/api/jobs/{job_id}/artifacts/{name}",
            # live (Phase 4a)
            "/api/live/start",
            "/api/live/stop",
            "/api/live/status",
            "/api/live/frame",
            "/api/live/stream",
        }
        assert "delete" in paths["/api/jobs/{job_id}"]

    def test_json_tra_ve_khong_co_bytes(self, client):
        """Response phải serialize được — chặn lỗi kiểu numpy/bytes lọt vào DTO."""
        job_id = _upload(client).json()["job_id"]
        json.dumps(client.get(f"/api/jobs/{job_id}").json())


class TestHopDongSummary:
    """Chốt hợp đồng `summary` giữa backend và frontend.

    Danh sách khoá dưới đây PHẢI khớp interface `JobSummary` trong `web/src/api.ts`.
    Bug thật 08-11 (ảnh chụp E2E): backend trả `lost_count` nhưng frontend đọc `lost_frames`
    → cột "Frame mất dấu" hiện "—" dù dữ liệu có. Test này chặn tái diễn.
    """

    KEYS_FRONTEND_DUNG = {
        "total_frames",
        "mean_latency_ms",
        "p95_latency_ms",
        "effective_fps",
        "lost_count",
        "lost_ratio",
        "reacquired_count",
    }

    def test_summary_co_du_khoa_frontend_can(self):
        from src.metrics_logger import FrameRecord, MetricsLogger

        logger = MetricsLogger()
        for index in range(3):
            logger.log(FrameRecord(frame_idx=index, latency_ms=175.0, score=2.0, center=(10, 10)))
        summary = logger.summary()

        missing = self.KEYS_FRONTEND_DUNG - set(summary)
        assert not missing, f"summary thiếu khoá mà web/src/api.ts cần: {sorted(missing)}"

    def test_khoa_lost_count_khong_phai_lost_frames(self):
        """Tên cũ `lost_frames` đã bỏ — nếu ai đó đổi về tên đó thì test này nhắc."""
        from src.metrics_logger import FrameRecord, MetricsLogger

        logger = MetricsLogger()
        logger.log(FrameRecord(frame_idx=0, latency_ms=100.0, score=1.0, center=None, lost=True))
        summary = logger.summary()

        assert summary["lost_count"] == 1
        assert "lost_frames" not in summary
