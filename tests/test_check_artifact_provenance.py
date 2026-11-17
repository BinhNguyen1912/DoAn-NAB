"""`scripts/check_artifact_provenance.py` — `git_rev` của artifact phải CÒN SỐNG và thuộc cây này.

Vì sao có file này (tách khỏi `tests/test_bang_cau_hinh.py`, P3 review 17-11): script là job CI
(`./run provcheck` → `--nghiem`), nên **mã thoát** mới là thứ CI dựa vào — phải có test gọi `main()`,
không chỉ test hàm phụ.

Ba trạng thái KHÔNG gộp: `chet` (không tồn tại — chặn khi `--nghiem`), `lech` (tồn tại nhưng không phải
tổ tiên của HEAD — cảnh báo), `ok-da-biet` (có trong allowlist kèm lý do — không chặn).
"""

import json

import pytest

from scripts import check_artifact_provenance as cap


def _artifact(thu_muc, ten, rev):
    (thu_muc / ten).write_text(json.dumps({"git_rev": rev, "cau_hinh": {}}), encoding="utf-8")


class TestPhanLoai:
    def test_rev_khong_phai_hex_la_chet(self):
        """`--help` từng được chấm `ok` (git hiểu option ở tầng trên, rc 0 cho cả hai lệnh)."""
        assert cap.phan_loai("--help") == "chet"
        assert cap.phan_loai("HEAD") == "chet"
        assert cap.phan_loai("") == "chet"
        assert cap.phan_loai(None) == "chet"

    def test_rev_that_la_ok(self):
        """`ee9f25672d72` là commit THẬT (commit sinh ra artifact `drift_2026-11-08`)."""
        assert cap.phan_loai("ee9f25672d72") == "ok"

    def test_rev_40_hex_bia_la_chet(self):
        assert cap.phan_loai("ee9f256a1e77e6b4de08b0b0b8f4b0f0b8f0b0b8") == "chet"


class TestQuet:
    def test_rev_trong_allowlist_la_chay_duoc(self, tmp_path):
        rev = "ee9f256a1e77e6b4de08b0b0b8f4b0f0b8f0b0b8"
        _artifact(tmp_path, "drift_2026-11-08_metrics.json", rev)
        ra = cap.quet(tmp_path, {("drift_2026-11-08_metrics.json", rev): "field 40-hex gõ tay"})
        assert ra[0]["trang_thai"] == "ok-da-biet"
        assert ra[0]["ghi_chu"] == "field 40-hex gõ tay"

    def test_rev_chet_moi_khong_duoc_allowlist(self, tmp_path):
        """Allowlist khoá theo (file, rev) ⇒ rev chết MỚI trong cùng file vẫn bị bắt."""
        _artifact(tmp_path, "moi_metrics.json", "deadbeef" + "0" * 32)
        assert cap.quet(tmp_path, cho_phep={})[0]["trang_thai"] == "chet"

    def test_artifact_hong_va_thieu_rev_deu_la_chet(self, tmp_path):
        (tmp_path / "hong_metrics.json").write_text("{khong-json", encoding="utf-8")
        _artifact(tmp_path, "thieu_metrics.json", None)
        ra = {r["file"]: r["trang_thai"] for r in cap.quet(tmp_path, cho_phep={})}
        assert ra == {"hong_metrics.json": "chet", "thieu_metrics.json": "chet"}

    def test_allowlist_co_ly_do_du_dai_va_nhac_commit_that(self):
        """Lý do phải đọc được VÀ nhắc commit thật (`ee9f2567`) — nếu không, lần "dọn" sau sẽ xoá mất
        manh mối duy nhất nối field hỏng về commit sinh số (P1 review 17-11)."""
        assert cap.CHO_PHEP, "allowlist không được rỗng (đang có 3 ca thật)"
        for (_file, _rev), ly_do in cap.CHO_PHEP.items():
            assert len(ly_do) > 30, "mỗi mục allowlist phải nêu lý do đọc được"
        assert any("ee9f2567" in ly_do for ly_do in cap.CHO_PHEP.values())


class TestMainMaThoat:
    """Mã thoát là thứ CI (`--nghiem`) dựa vào ⇒ phải có test gọi `main()`."""

    def test_rev_chet_moi_thi_nghiem_tra_1(self, tmp_path):
        _artifact(tmp_path, "moi_metrics.json", "deadbeef" + "0" * 32)
        assert cap.main(["--thu-muc", str(tmp_path), "--nghiem"]) == 1

    def test_khong_nghiem_chi_canh_bao(self, tmp_path):
        _artifact(tmp_path, "moi_metrics.json", "deadbeef" + "0" * 32)
        assert cap.main(["--thu-muc", str(tmp_path)]) == 0

    def test_allowlist_khong_lam_do(self, tmp_path):
        rev = "ee9f256a1e77e6b4de08b0b0b8f4b0f0b8f0b0b8"
        _artifact(tmp_path, "drift_2026-11-08_metrics.json", rev)
        assert cap.main(["--thu-muc", str(tmp_path), "--nghiem"]) == 0

    def test_thu_muc_rong_la_ma_2_khong_phai_xanh_im_lang(self, tmp_path, capsys):
        """`0 artifact` KHÔNG phải "đã kiểm": glob ngừng khớp mà CI vẫn xanh là bẫy `0/None`."""
        assert cap.main(["--thu-muc", str(tmp_path), "--nghiem"]) == 2
        assert "không phải" in capsys.readouterr().out

    def test_thu_muc_khong_ton_tai_la_ma_2(self, tmp_path):
        assert cap.main(["--thu-muc", str(tmp_path / "khong-co"), "--nghiem"]) == 2

    @pytest.mark.parametrize("ten", ["bang_cau_hinh_2026-11-15_metrics.json"])
    def test_rev_lech_chi_canh_bao_khong_chan(self, tmp_path, ten):
        """Rev tồn tại nhưng KHÔNG phải tổ tiên của HEAD ⇒ `lech`, không chặn (artifact cũ hợp lệ)."""
        _artifact(tmp_path, ten, "ee9f25672d72")
        ra = cap.quet(tmp_path, cho_phep={})
        assert ra[0]["trang_thai"] in {"ok", "lech"}
