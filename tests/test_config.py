"""Test Config loader — tham số hoá qua YAML (ticket 08, story 18).

Không cần model: test loader thuần + thứ tự ưu tiên defaults < YAML < CLI.
"""
import os
import textwrap

import pytest

from src.config import (
    DEFAULTS,
    load_config,
    merge_cli_overrides,
    resolve_checkpoint,
    REPO_ROOT,
)


def _write_yaml(tmp_path, text):
    path = tmp_path / "config.yaml"
    path.write_text(textwrap.dedent(text), encoding="utf-8")
    return str(path)


class TestLoadConfig:
    def test_khong_file_tra_defaults(self, tmp_path):
        """--config bỏ trống → defaults (không bắt buộc có file)."""
        cfg = load_config(None)
        assert cfg == DEFAULTS

    def test_file_thieu_da_ghi_roi(self, tmp_path):
        cfg = load_config(_write_yaml(tmp_path, """
            checkpoint: samurai/sam2/checkpoints/does-not-exist.pt
            source: 0
            """))
        # chỉ 2 key được override, còn lại giữ defaults
        assert cfg["record_enabled"] is DEFAULTS["record_enabled"]

    def test_override_hoan_toan_bang_yaml(self, tmp_path):
        cfg = load_config(_write_yaml(tmp_path, """
            checkpoint: samurai/sam2/checkpoints/sam2.1_hiera_tiny.pt
            source: 2
            max_trajectory: 40
            record_enabled: true
            record_path: data/abc.mp4
            """))
        assert cfg["source"] == 2
        assert cfg["max_trajectory"] == 40
        assert cfg["record_enabled"] is True
        assert cfg["record_path"] == "data/abc.mp4"
        assert cfg["record_fps"] == DEFAULTS["record_fps"]  # không đụng key khác

    def test_source_chap_nhan_int_hoac_file_path(self, tmp_path):
        """source là webcam int HOẶC đường dẫn file/RTSP — cả hai hợp lệ."""
        cfg = load_config(_write_yaml(tmp_path, """
            source: data/_smoke8.avi
            """))
        assert cfg["source"] == "data/_smoke8.avi"

    def test_yaml_sai_kieu_bao_loi_ro_rang(self, tmp_path):
        """max_trajectory phải là số — YAML sai kiểu báo lỗi dễ hiểu."""
        with pytest.raises(ValueError, match="max_trajectory"):
            load_config(_write_yaml(tmp_path, """
                max_trajectory: many-frames
                """))

    def test_yaml_file_khong_ton_tai(self):
        with pytest.raises(FileNotFoundError):
            load_config("khong-ton-tai.yaml")


class TestMergeCli:
    def test_cli_override_yaml_gia_tri_null(self):
        """CLI chỉ đè khi giá trị khác None (flag không truyền → YAML thắng)."""
        cfg = {"source": "data/a.mp4", "record_path": None}
        out = merge_cli_overrides(cfg, {"record_path": None, "source": 0})
        assert out["record_path"] is None          # CLI không chỉ định → giữ YAML
        assert out["source"] == 0                  # CLI chỉ định → đè YAML

    def test_cli_khong_dong_key_ngoai_cfg(self):
        out = merge_cli_overrides({"a": 1}, {"b": 2})
        assert "b" not in out  # chỉ hợp nhất key có sẵn trong cfg


class TestResolveCheckpoint:
    def test_duong_dan_tuong_doi_giai_theo_repo_root(self):
        resolved = resolve_checkpoint("samurai/sam2/checkpoints/sam2.1_hiera_tiny.pt")
        assert resolved.startswith(str(REPO_ROOT))
        assert resolved.endswith(".pt")

    def test_duong_dan_tuyet_doi_giu_nguyen(self):
        """File có sẵn dạng tuyệt đối → giữ nguyên (không nối REPO_ROOT lần nữa)."""
        p = os.path.join(REPO_ROOT, "requirements.txt")
        assert resolve_checkpoint(p) == p

    def test_file_khong_ton_tai_bao_loi_ro_rang(self):
        from pathlib import Path
        missing = str(Path(REPO_ROOT) / "data" / "khong_co.pt")
        with pytest.raises(FileNotFoundError, match="tải checkpoint"):
            resolve_checkpoint(missing)


class TestDefaults:
    def test_defaults_khong_bat_ghi_video(self):
        """An toàn mặc định: không ghi mp4 ngoài ý muốn (record_enabled False)."""
        assert DEFAULTS["record_enabled"] is False

    def test_defaults_checkpoint_tiny_samurai(self):
        assert "sam2.1_hiera_tiny" in DEFAULTS["checkpoint"]