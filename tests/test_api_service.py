"""Test JobService — điều phối use case với adapter GIẢ (không HTTP, không model, không subprocess)."""

import io

import pytest

from src.api.domain import (
    InvalidBBox,
    JobConflict,
    JobNotFound,
    JobState,
    PayloadTooLarge,
    RunnerStartFailed,
    UnsupportedMedia,
)

BOX = (2, 2, 20, 16)


def _stream(data: bytes = b"video-gia") -> io.BytesIO:
    return io.BytesIO(data)


def _create(service, name="v.mp4", params=None):
    return service.create_job(
        original_name=name, stream=_stream(), params=params or {"cue": "object"}
    )


class TestCreateJob:
    def test_tao_job_luu_video_va_dat_trang_thai_uploaded(self, service, fs_store):
        job = _create(service)

        assert fs_store.get(job.job_id) is not None
        assert (fs_store.path(job.job_id) / "source.mp4").read_bytes() == b"video-gia"
        status = fs_store.read_status(job.job_id)
        assert status.state is JobState.UPLOADED
        assert "chờ chọn đối tượng" in status.message

    @pytest.mark.parametrize("name", ["tailieu.txt", "video.wmv", ""])
    def test_dinh_dang_khong_ho_tro_bi_tu_choi(self, service, name):
        with pytest.raises(UnsupportedMedia):
            service.create_job(original_name=name, stream=_stream(), params={})

    def test_cue_la_bi_tu_choi(self, service):
        with pytest.raises(UnsupportedMedia):
            _create(service, params={"cue": "lung-tung"})

    def test_video_qua_lon_thi_xoa_job_rac(self, service, fs_store, api_settings):
        """Vượt giới hạn → ném PayloadTooLarge và KHÔNG để lại thư mục job."""
        big = _stream(b"x" * (api_settings.max_upload_bytes + 10))

        with pytest.raises(PayloadTooLarge):
            service.create_job(original_name="v.mp4", stream=big, params={})

        assert fs_store.list_ids(100) == []


class TestSelect:
    def test_select_khoi_chay_pipeline_va_luu_bbox(self, service, fs_store, fake_runner):
        job = _create(service)
        service.select(job.job_id, BOX)

        assert fake_runner.started == [(job.job_id, {"cue": "object"}, BOX)]
        assert fs_store.get(job.job_id).bbox == BOX
        assert fs_store.read_status(job.job_id).state is JobState.RUNNING

    def test_select_job_khong_ton_tai(self, service):
        with pytest.raises(JobNotFound):
            service.select("20260101-000000-abcdef", BOX)

    def test_select_lan_hai_khi_dang_chay_bi_chan(self, service):
        job = _create(service)
        service.select(job.job_id, BOX)
        with pytest.raises(JobConflict):
            service.select(job.job_id, BOX)

    def test_select_khi_da_done_bi_chan(self, service, fake_runner):
        job = _create(service)
        service.select(job.job_id, BOX)
        fake_runner.complete(job.job_id, 0, summary={"total_frames": 3})
        with pytest.raises(JobConflict):
            service.select(job.job_id, BOX)

    def test_bbox_vuot_khung_bi_tu_choi(self, service, fake_probe):
        fake_probe.size = (64, 48)
        job = _create(service)
        with pytest.raises(InvalidBBox, match="64x48"):
            service.select(job.job_id, (60, 0, 20, 10))

    def test_runner_khong_khoi_dong_duoc_thi_job_ve_error(self, service, fs_store, fake_runner):
        job = _create(service)
        fake_runner.fail_start = True
        with pytest.raises(RunnerStartFailed):
            service.select(job.job_id, BOX)

        status = fs_store.read_status(job.job_id)
        assert status.state is JobState.ERROR
        assert "không chạy được" in status.message.lower()


class TestStatusVaTienTrinh:
    def test_job_uploaded_giu_nguyen_trang_thai(self, service):
        job = _create(service)
        view = service.status(job.job_id)
        assert view.status.state is JobState.UPLOADED
        assert view.summary is None

    def test_dang_chay_doc_tien_trinh_that_tu_progress(self, service, fake_runner):
        job = _create(service)
        service.select(job.job_id, BOX)
        fake_runner.progress[job.job_id] = {"frames": 50, "total": 100}

        view = service.status(job.job_id)
        assert view.status.state is JobState.RUNNING
        assert view.status.progress == 50     # literal: 50/100

    def test_chua_biet_tong_thi_giu_phan_tram_cu(self, service, fake_runner):
        job = _create(service)
        service.select(job.job_id, BOX)
        fake_runner.progress[job.job_id] = {"frames": 7, "total": None}

        assert service.status(job.job_id).status.progress == 0

    def test_co_summary_va_da_xong_thi_done_100(self, service, fake_runner):
        job = _create(service)
        service.select(job.job_id, BOX)
        fake_runner.summaries[job.job_id] = {"total_frames": 5}
        fake_runner.running.discard(job.job_id)      # pipeline đã thoát hẳn

        view = service.status(job.job_id)
        assert view.status.state is JobState.DONE
        assert view.status.progress == 100
        assert view.summary == {"total_frames": 5}

    def test_co_summary_nhung_con_dang_xuat_ban_thi_van_running(self, service, fake_runner):
        """Bug thật 08-11 (E2E): summary.json có TRƯỚC khi xuất out_web.mp4.

        Nếu báo done sớm, UI hiện player khi chưa có bản H.264 → Chrome không phát được.
        """
        job = _create(service)
        service.select(job.job_id, BOX)
        fake_runner.summaries[job.job_id] = {"total_frames": 5}
        # vẫn còn trong fake_runner.running = đang hoàn tất (xuất H.264)

        view = service.status(job.job_id)
        assert view.status.state is JobState.RUNNING
        assert view.status.progress < 100

    def test_tien_trinh_chet_khong_co_ket_qua_thi_error(self, service, fake_runner, fs_store):
        """Ca server restart: không còn process, không có summary → phải báo lỗi rõ ràng."""
        job = _create(service)
        service.select(job.job_id, BOX)
        fake_runner.running.discard(job.job_id)          # process biến mất (không gọi callback)

        status = service.status(job.job_id).status
        assert status.state is JobState.ERROR
        assert "worker.log" in status.message

    def test_callback_ket_thuc_that_bai_ghi_error(self, service, fake_runner, fs_store):
        job = _create(service)
        service.select(job.job_id, BOX)
        fake_runner.complete(job.job_id, 2)

        status = fs_store.read_status(job.job_id)
        assert status.state is JobState.ERROR
        assert "mã 2" in status.message


class TestListingVaArtifact:
    def test_liet_ke_moi_nhat_truoc(self, service, fs_store):
        """Sắp theo created_at (mili-giây) — tạo cách nhau để thứ tự xác định."""
        import time

        first = _create(service)
        time.sleep(0.02)          # đủ để created_at khác nhau ở độ phân giải mili-giây
        second = _create(service)

        ids = [view.job.job_id for view in service.listing()]
        assert ids == [second.job_id, first.job_id]

    def test_artifact_chi_hien_khi_file_ton_tai(self, service, fs_store, fake_runner):
        job = _create(service)
        assert service.status(job.job_id).artifacts == {}

        (fs_store.path(job.job_id) / "out.mp4").write_bytes(b"x")
        assert service.status(job.job_id).artifacts == {
            "out.mp4": f"/api/jobs/{job.job_id}/artifacts/out.mp4"
        }

    def test_ban_web_h264_duoc_lieu_ke_nhu_artifact(self, service, fs_store):
        """UI cần out_web.mp4 (H.264) — thiếu nó thì Chrome không phát được video."""
        job = _create(service)
        (fs_store.path(job.job_id) / "out.mp4").write_bytes(b"x")
        (fs_store.path(job.job_id) / "out_web.mp4").write_bytes(b"x")

        artifacts = service.status(job.job_id).artifacts
        assert "out_web.mp4" in artifacts
        assert artifacts["out_web.mp4"].endswith("/artifacts/out_web.mp4")

    def test_artifact_ngoai_whitelist_bi_chan(self, service, fs_store):
        job = _create(service)
        (fs_store.path(job.job_id) / "job.json").write_text("{}", encoding="utf-8")
        assert service.artifact_path(job.job_id, "job.json") is None
        assert service.artifact_path(job.job_id, "../job.json") is None


class TestDeleteVaPreview:
    def test_xoa_job(self, service, fs_store):
        job = _create(service)
        service.delete(job.job_id)
        assert fs_store.get(job.job_id) is None

    def test_xoa_job_dang_chay_bi_chan(self, service, fake_runner):
        job = _create(service)
        service.select(job.job_id, BOX)
        with pytest.raises(JobConflict):
            service.delete(job.job_id)

    def test_preview_di_qua_probe(self, service, fake_probe):
        job = _create(service)
        assert service.preview(job.job_id) == b"\xff\xd8fake-jpeg"
        assert fake_probe.requests[-1][1] == 0        # index frame mặc định

    def test_preview_chuyen_tiep_index_frame(self, service, fake_probe):
        job = _create(service)
        service.preview(job.job_id, index=7)
        assert fake_probe.requests[-1][1] == 7

    def test_preview_job_khong_ton_tai(self, service):
        with pytest.raises(JobNotFound):
            service.preview("20260101-000000-abcdef")
