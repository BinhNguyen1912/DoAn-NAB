"""Test tầng miền (`src/api/domain.py`) — thuần logic, không I/O, không HTTP, không model."""

import pytest

from src.api.domain import (
    ACTIVE_STATES,
    InvalidBBox,
    JobState,
    JobStatus,
    assert_bbox_inside,
    can_select,
    clamp_percent,
    parse_state,
    progress_percent,
)


class TestParseState:
    @pytest.mark.parametrize("value,expected", [
        ("uploaded", JobState.UPLOADED),
        ("queued", JobState.QUEUED),
        ("running", JobState.RUNNING),
        ("done", JobState.DONE),
        ("error", JobState.ERROR),
    ])
    def test_doc_dung_trang_thai_hop_le(self, value, expected):
        assert parse_state(value) is expected

    @pytest.mark.parametrize("value", [None, "", "khong-ton-tai", 123])
    def test_gia_tri_la_tra_ve_uploaded_khong_no(self, value):
        """Dữ liệu cũ/hỏng không được làm sập API."""
        assert parse_state(value) is JobState.UPLOADED


class TestProgressPercent:
    def test_chia_dung_theo_tong(self):
        # literal tính tay: 50/200 = 25%
        assert progress_percent(50, 200) == 25

    def test_khong_bao_gio_bao_100_khi_dang_chay(self):
        assert progress_percent(200, 200) == 99

    @pytest.mark.parametrize("total", [None, 0, -5])
    def test_chua_biet_tong_tra_none(self, total):
        """Webcam/stream không có tổng frame → caller tự quyết, không được đoán."""
        assert progress_percent(10, total) is None

    def test_frame_am_duoc_kep_ve_0(self):
        assert progress_percent(-10, 100) == 0


class TestClampPercent:
    @pytest.mark.parametrize("value,expected", [(-5, 0), (0, 0), (42.4, 42), (100, 100), (180, 100)])
    def test_kep_ve_khoang_0_100(self, value, expected):
        assert clamp_percent(value) == expected


class TestCanSelect:
    def test_uploaded_va_error_cho_chon_lai(self):
        assert can_select(JobStatus(JobState.UPLOADED)) is True
        assert can_select(JobStatus(JobState.ERROR)) is True

    @pytest.mark.parametrize("state", [JobState.QUEUED, JobState.RUNNING, JobState.DONE])
    def test_cac_trang_thai_con_lai_bi_chan(self, state):
        assert can_select(JobStatus(state)) is False

    def test_active_states_chi_gom_queued_va_running(self):
        assert ACTIVE_STATES == {JobState.QUEUED, JobState.RUNNING}


class TestAssertBboxInside:
    def test_bbox_hop_le_khong_nem(self):
        assert_bbox_inside((10, 10, 20, 20), (64, 48))

    def test_bbox_vuot_mep_phai_bi_tu_choi(self):
        with pytest.raises(InvalidBBox, match="64x48"):
            assert_bbox_inside((60, 0, 20, 10), (64, 48))

    @pytest.mark.parametrize("box", [(0, 0, 0, 10), (0, 0, 10, 0), (-1, 0, 10, 10), (0, -1, 10, 10)])
    def test_bbox_khong_hop_le_ve_kich_thuoc(self, box):
        with pytest.raises(InvalidBBox):
            assert_bbox_inside(box, (64, 48))

    def test_khong_doc_duoc_video_thi_chi_kiem_tra_kich_thuoc(self):
        """probe_size None (video hỏng) vẫn phải chặn được bbox rỗng."""
        assert_bbox_inside((0, 0, 10, 10), None)
        with pytest.raises(InvalidBBox):
            assert_bbox_inside((0, 0, 0, 10), None)
