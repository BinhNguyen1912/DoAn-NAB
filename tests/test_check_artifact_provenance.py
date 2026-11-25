"""`scripts/check_artifact_provenance.py` — `git_rev` của artifact phải CÒN SỐNG và thuộc cây này.

Vì sao có file này (tách khỏi `tests/test_bang_cau_hinh.py`, P3 review 17-11): script là job CI
(`./run provcheck` → `--nghiem`), nên **mã thoát** mới là thứ CI dựa vào — phải có test gọi `main()`,
không chỉ test hàm phụ.

Ba trạng thái KHÔNG gộp: `chet` (không tồn tại — chặn khi `--nghiem`), `lech` (tồn tại nhưng không phải
tổ tiên của HEAD — cảnh báo), `ok-da-biet` (có trong allowlist kèm lý do — không chặn).
"""

import json


from scripts import check_artifact_provenance as cap


def _artifact(thu_muc, ten, rev):
    (thu_muc / ten).write_text(json.dumps({"git_rev": rev, "cau_hinh": {}}), encoding="utf-8")


class TestPhanLoai:
    def test_rev_khong_phai_hex_la_chet(self):
        """`--help` từng được chấm `ok` (git hiểu option ở tầng trên, rc 0 cho cả hai lệnh)."""
        assert cap.phan_loai("--help") == "chet"
        assert cap.phan_loai("HEAD") == "chet"
        # `""` và `None` = KHÔNG khai rev (schema cũ) — nhãn RIÊNG, không phải "rev chết" (25-11).
        assert cap.phan_loai("") == "thieu-rev"
        assert cap.phan_loai(None) == "thieu-rev"

    def test_rev_that_la_ok(self):
        """Rev của `HEAD` là tổ tiên của chính nó ⇒ `ok`.

        KHÔNG dùng một commit cũ cụ thể (`ee9f256…`): job pytest của CI là **shallow** (`fetch-depth`
        mặc định = 1) nên commit cũ không tồn tại ở đó và test sẽ đỏ oan — đúng bài học "test phụ thuộc
        môi trường" (CI đỏ lần đầu vì đúng lý do này).
        """
        import subprocess

        head = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
        assert cap.phan_loai(head) == "ok"

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
        """Allowlist khoá theo (file, rev) ⇒ rev chết MỚI trong CÙNG file vẫn bị bắt."""
        _artifact(tmp_path, "moi_metrics.json", "deadbeef" + "0" * 32)
        # Allowlist có đúng TÊN FILE đó nhưng rev KHÁC ⇒ không được hạ (khoá phải gồm cả rev).
        cho_phep = {("moi_metrics.json", "deadbeef" + "1" * 32): "lý do"}
        assert cap.quet(tmp_path, cho_phep=cho_phep)[0]["trang_thai"] == "chet"

    def test_moi_record_deu_co_khoa_goc(self, tmp_path):
        """Schema ĐỒNG NHẤT + GIÁ TRỊ đúng: artifact hỏng ⇒ `chet`; rev là HEAD ⇒ `ok`.

        (Bản trước dùng rev bịa `abcdef1` nên chỉ chạm nhánh `chet` và assert lỏng `in ("ok","lech",
        "chet")` — P3 review 18-11.)
        """
        import subprocess

        head = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True,
                              cwd=cap._REPO_ROOT).stdout.strip()
        (tmp_path / "hong_metrics.json").write_text("{khong-json", encoding="utf-8")
        _artifact(tmp_path, "ok_metrics.json", head)
        goc = {r["file"]: r["goc"] for r in cap.quet(tmp_path, cho_phep={})}
        assert goc == {"hong_metrics.json": "chet", "ok_metrics.json": "ok"}, goc

    def test_artifact_hong_la_chet_con_thieu_rev_la_nhan_rieng(self, tmp_path):
        """25-11: tách "rev CHẾT" khỏi "CHƯA TỪNG khai rev".

        Gộp hai chuyện này làm MỘT (bản trước) khiến 9 artifact schema cũ (trước luật provenance) bị
        tính là "chết" ⇒ job CI `git_rev của artifact` đỏ liên tục từ 22-11 ⇒ cổng mất tác dụng. Nay
        `thieu-rev` là nhãn riêng và allowlist theo TÊN, nên file MỚI thiếu `git_rev` vẫn bị bắt.
        """
        (tmp_path / "hong_metrics.json").write_text("{khong-json", encoding="utf-8")
        _artifact(tmp_path, "thieu_metrics.json", None)
        ra = {r["file"]: r["trang_thai"] for r in cap.quet(tmp_path, cho_phep={})}
        assert ra == {"hong_metrics.json": "chet", "thieu_metrics.json": "thieu-rev"}

    def test_allowlist_khong_rev_theo_ten_va_co_ly_do(self):
        """Artifact schema cũ: allowlist theo TÊN (không theo rev vì không có rev) + lý do rõ."""
        assert cap.CHO_PHEP_KHONG_REV, "danh sách artifact schema cũ không được rỗng"
        for ten, ly_do in cap.CHO_PHEP_KHONG_REV.items():
            assert ten.endswith("_metrics.json"), ten
            assert len(ly_do) > 30, f"`{ten}` phải nêu lý do đọc được"

    def test_thieu_rev_ten_moi_van_bi_bat(self, tmp_path):
        """Cổng còn răng: file KHÔNG nằm trong allowlist mà thiếu `git_rev` ⇒ vẫn là `thieu-rev`."""
        _artifact(tmp_path, "moi_hoan_toan_metrics.json", None)
        ra = {r["file"]: r["trang_thai"] for r in cap.quet(tmp_path, cho_phep={})}
        assert ra == {"moi_hoan_toan_metrics.json": "thieu-rev"}

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

    def test_rev_lech_chi_canh_bao_khong_chan(self, tmp_path, monkeypatch):
        """Rev tồn tại nhưng KHÔNG phải tổ tiên của HEAD ⇒ `lech`, không chặn (artifact cũ hợp lệ).

        `phan_loai` được giả lập vì "một commit tồn tại mà không phải tổ tiên" không dựng được chắc
        chắn trong repo shallow của CI.
        """
        _artifact(tmp_path, "cu_metrics.json", "1" * 40)
        monkeypatch.setattr(cap, "phan_loai", lambda _rev: "lech")
        assert cap.main(["--thu-muc", str(tmp_path), "--nghiem"]) == 0
        assert cap.quet(tmp_path, cho_phep={})[0]["trang_thai"] == "lech"

    def test_rev_lech_trong_allowlist_duoc_ha_xuong_da_biet(self, tmp_path, monkeypatch):
        """`lech` CỐ ĐỊNH (rev chỉ tồn tại ở object local vì nhánh rebase trước khi push) phải vào
        allowlist như `chet`, nếu không dòng "2 lệch" luôn hiện và **che mất `lech` MỚI** — đúng lớp
        "cảnh báo cố định làm nhiễu cổng kiểm" (AGENTS §6: cổng phải kêu khi có chuyện mới)."""
        _artifact(tmp_path, "bi_rebase_metrics.json", "2" * 40)
        monkeypatch.setattr(cap, "phan_loai", lambda _rev: "lech")
        cho_phep = {("bi_rebase_metrics.json", "2" * 40): "nhánh rebase trước khi push — CẤM dẫn rev"}
        ra = cap.quet(tmp_path, cho_phep=cho_phep)
        assert ra[0]["trang_thai"] == "ok-da-biet", ra
        # Nhãn GỐC không được mất: "đã biết" vì rev CHẾT khác với "đã biết" vì rev còn sống mà không
        # phải tổ tiên (P2 review 18-11: bản trước in "3 chết-đã-biết" trong khi 2/3 là `lech`).
        assert ra[0]["goc"] == "lech", ra
        assert ra[0]["ghi_chu"]

    def test_rev_lech_MOI_van_la_lech(self, tmp_path, monkeypatch):
        """Allowlist không được nuốt `lech` của artifact KHÁC (khoá gồm cả tên file)."""
        # CÙNG rev, KHÁC tên file: mutant "chỉ so rev" sẽ hạ nhầm mục này ⇒ test phải đỏ.
        # (Kịch bản thật: nhiều artifact dùng chung một rev — `bang_cau_hinh_*`, `ab_*`.)
        _artifact(tmp_path, "moi_metrics.json", "3" * 40)
        monkeypatch.setattr(cap, "phan_loai", lambda _rev: "lech")
        cho_phep = {("bi_rebase_metrics.json", "3" * 40): "lý do"}
        assert cap.quet(tmp_path, cho_phep=cho_phep)[0]["trang_thai"] == "lech"

    def test_tong_ket_tach_nhan_goc_lech_va_chet(self, tmp_path, monkeypatch, capsys):
        """Nhãn IN RA phải giữ trạng thái gốc: `ok-da-biet(lech)` và `ok-da-biet(chet)`.

        Bản trước của test này **không có răng**: nó truyền allowlist cho `quet()` (kết quả vứt đi) còn
        `main()` dùng `CHO_PHEP` của module ⇒ record là `lech`, và assert `"đã-biết" in out` xanh nhờ
        dòng tổng kết luôn in literal "0 đã-biết". Phải **vá `CHO_PHEP` trên module** mới đi đúng đường
        (P2 review 18-11).
        """
        _artifact(tmp_path, "a_metrics.json", "2" * 40)      # phan_loai ⇒ lech (rev còn sống)
        _artifact(tmp_path, "b_metrics.json", "3" * 40)      # phan_loai ⇒ chet (rev mất hẳn)
        monkeypatch.setattr(cap, "phan_loai", lambda rev: "lech" if rev == "2" * 40 else "chet")
        monkeypatch.setattr(cap, "CHO_PHEP", {("a_metrics.json", "2" * 40): "lý do lech",
                                             ("b_metrics.json", "3" * 40): "lý do chet"})
        assert cap.main(["--thu-muc", str(tmp_path)]) == 0
        out = capsys.readouterr().out
        assert "ok-da-biet(lech)" in out, out
        assert "ok-da-biet(chet)" in out, out
        assert "2 đã-biết" in out, out
        assert "chết-đã-biết" not in out, out

    def test_nghiem_lech_khong_do_vi_lech_DA_ALLOWLIST(self, tmp_path, monkeypatch):
        """`lech` đã nằm trong `CHO_PHEP` KHÔNG được làm `--nghiem-lech` đỏ — nếu không, cờ này đỏ vĩnh
        viễn trên `main` (nơi có 2 mục 10-11), tức tái hiện đúng lỗi "cảnh báo cố định" mà #44 vừa sửa."""
        _artifact(tmp_path, "a_metrics.json", "2" * 40)
        monkeypatch.setattr(cap, "phan_loai", lambda _rev: "lech")
        monkeypatch.setattr(cap, "CHO_PHEP", {("a_metrics.json", "2" * 40): "lý do"})
        assert cap.main(["--thu-muc", str(tmp_path), "--nghiem-lech"]) == 0

    def test_nghiem_lech_opt_in(self, tmp_path, monkeypatch):
        """`--nghiem-lech` chặn `lech`; mặc định KHÔNG chặn (lech là trạng thái hợp lệ trước merge)."""
        _artifact(tmp_path, "a_metrics.json", "2" * 40)
        monkeypatch.setattr(cap, "phan_loai", lambda _rev: "lech")
        assert cap.main(["--thu-muc", str(tmp_path), "--nghiem"]) == 0
        assert cap.main(["--thu-muc", str(tmp_path), "--nghiem-lech"]) == 1

    def test_nghiem_lech_khong_bi_nuot_khi_co_chet(self, tmp_path, monkeypatch):
        """`--nghiem-lech` phải còn tác dụng khi có `chet` mà KHÔNG có `--nghiem`.

        Bản trước `return 1 if args.nghiem else 0` ở nhánh `chet` ⇒ cờ bị nuốt, exit 0 (đã diễn tập:
        trả lại `return` sớm thì exit 0, đúng ca sai). Chỉ với tới được khi gọi script trực tiếp
        (`./run provcheck` luôn chèn `--nghiem`).
        """
        _artifact(tmp_path, "a_metrics.json", "2" * 40)                      # ⇒ lech
        _artifact(tmp_path, "b_metrics.json", "3" * 40)                      # ⇒ chet
        monkeypatch.setattr(cap, "phan_loai", lambda rev: "lech" if rev == "2" * 40 else "chet")
        # Có `chet` nên nhánh cũ `return 1 if args.nghiem else 0` trả 0 NGAY ⇒ `--nghiem-lech` bị nuốt
        # (diễn tập: trả lại `return` sớm thì ra 0). Đúng phải là 1 vì có `lech` và cờ lech đã bật.
        assert cap.main(["--thu-muc", str(tmp_path), "--nghiem-lech"]) == 1
        assert cap.main(["--thu-muc", str(tmp_path)]) == 0                   # không cờ ⇒ chỉ cảnh báo
