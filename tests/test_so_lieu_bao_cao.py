"""Test `scripts/so_lieu_bao_cao.py` — bảng số báo cáo phải SINH từ artifact, không chép tay.

Vì sao: số trong báo cáo từng trôi khỏi artifact (sửa tay rồi quên), và `None` (chưa đo) từng bị in
thành `0`. Hai bẫy đó phải đỏ ngay ở test, không đợi tới lúc trích vào slide.
"""

import json

import pytest

import scripts.so_lieu_bao_cao as so_lieu


class TestLayGiaTri:
    """`_get` — đường dẫn khoá `"a.b.0.c"`, thiếu khúc nào cũng phải là THIẾU (không bịa)."""

    def test_lay_duoc_khoa_long_nhau(self):
        data = {"a": {"b": [{"c": 7}]}}
        assert so_lieu._get(data, "a.b.0.c") == 7

    def test_thieu_khoa_tra_thieu(self):
        assert so_lieu._get({"a": {"b": 1}}, "a.z") is so_lieu._THIEU

    def test_chi_so_ngoai_mang_tra_thieu(self):
        assert so_lieu._get({"a": [1]}, "a.5") is so_lieu._THIEU

    def test_chi_so_khong_phai_so_tra_thieu(self):
        assert so_lieu._get({"a": [1]}, "a.x") is so_lieu._THIEU


class TestDinhDang:
    """`None` = CHƯA ĐO (in `null`), thiếu artifact/khoá = `THIẾU`; hai thứ KHÔNG được in thành 0."""

    def test_none_in_la_null_chua_do(self):
        assert "chưa đo" in so_lieu._fmt(None)

    def test_thieu_in_hoa(self):
        assert so_lieu._fmt(so_lieu._THIEU) == "THIẾU"

    def test_khong_bao_gio_in_0_cho_thieu(self):
        assert so_lieu._fmt(so_lieu._THIEU) != "0"
        assert so_lieu._fmt(None) != "0"

    def test_so_thuc_dung_dau_phay_viet_nam(self):
        assert so_lieu._fmt(0.8922) == "0,8922"


class TestRegistryKhopArtifact:
    """Mọi dòng của registry phải trỏ được tới artifact + khoá có thật trong repo."""

    def test_moi_dong_co_du_5_truong(self):
        for row in so_lieu.REGISTRY:
            assert len(row) == 5, f"dòng thiếu trường: {row}"
            assert row[4].strip(), f"dòng {row[0]!r} thiếu cảnh báo 'CẤM trích thành'"

    def test_artifact_va_khoa_ton_tai(self):
        for claim, artifact, key, _unit, _cam in so_lieu.REGISTRY:
            path = so_lieu._REPO_ROOT / artifact
            assert path.exists(), f"thiếu artifact {artifact} (dòng {claim!r})"
            data = json.loads(path.read_text(encoding="utf-8"))
            assert so_lieu._get(data, key) is not so_lieu._THIEU, (
                f"khoá {key!r} không có trong {artifact} (dòng {claim!r})"
            )


def test_bang_co_ca_hai_cot_quan_trong():
    table = so_lieu.build_table()
    assert "CẤM trích thành" in table
    assert table.count("\n") >= len(so_lieu.REGISTRY), "bảng phải có 1 dòng mỗi tuyên bố"


def test_check_bao_lech_khi_file_khac_ban_sinh(tmp_path, monkeypatch):
    """`--check` là thứ CI dùng: file đã commit lệch artifact ⇒ mã thoát 1 (không im lặng)."""
    out = tmp_path / "so-lieu.md"
    out.write_text("nội dung cũ\n", encoding="utf-8")
    monkeypatch.setattr(so_lieu.sys, "argv", ["so_lieu_bao_cao.py", "--out", str(out), "--check"])
    assert so_lieu.main() == 1

    out.write_text(so_lieu.build_document(), encoding="utf-8")
    assert so_lieu.main() == 0


def test_doc_da_commit_khop_artifact():
    """`docs/so-lieu-bao-cao.md` ĐÃ COMMIT phải khớp bản sinh ra (CI không chạy `--check`).

    Không có test này thì file có thể trôi khỏi artifact mà không gì đỏ (review vòng 3, P2).
    """
    da_commit = (so_lieu._REPO_ROOT / "docs/so-lieu-bao-cao.md").read_text(encoding="utf-8")
    assert da_commit == so_lieu.build_document(), (
        "docs/so-lieu-bao-cao.md lệch artifact — chạy `python scripts/so_lieu_bao_cao.py` rồi commit"
    )


@pytest.mark.parametrize("artifact", sorted({row[1] for row in so_lieu.REGISTRY}))
def test_artifact_trong_bang_phai_co_provenance(artifact):
    """Mọi artifact được trích phải có `git_rev` và KHÔNG bẩn (AGENTS §6).

    Chấp nhận `git_dirty_code == false` (artifact mới) **hoặc** `git_dirty == false` (artifact cũ chỉ
    có trường này, ví dụ `data/occlusion_metrics_320_metrics.json`).
    """
    data = json.loads((so_lieu._REPO_ROOT / artifact).read_text(encoding="utf-8"))
    assert data.get("git_rev"), f"{artifact} thiếu git_rev"
    assert data.get("git_loi") in (None, ""), f"{artifact} có git_loi ⇒ không có provenance"
    assert data.get("git_dirty_code") is False or data.get("git_dirty") is False, (
        f"{artifact} được đo trên cây bẩn ⇒ không được trích"
    )
