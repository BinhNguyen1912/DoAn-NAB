"""Test cho `tools/label_ui.py` — UI gán nhãn "bắt đúng / sai" cho phiên đã quay.

Không cần trình duyệt: kiểm phần **số học + lưu nhãn + API** bằng HTTP thật trên cổng 0.
"""
import json
import threading
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import pytest

from tools import label_ui as L

REPO = Path(__file__).resolve().parents[1]


def _csv(tmp_path, ten="demoip_test", rows=None):
    rows = rows or [
        # (frame_idx, latency_ms, center_x, center_y, bbox_w, bbox_h, mask_area, nghi)
        (0, 300, 100, 100, 40, 60, 2400, ""),
        (1, 200, 110, 100, 40, 60, 2400, ""),
        (2, 500, 300, 300, 80, 90, 7200, "1"),
        (3, 200, None, None, None, None, 0, ""),
    ]
    p = tmp_path / f"{ten}_metrics.csv"
    with p.open("w", encoding="utf-8", newline="") as f:
        w = __import__("csv").writer(f)
        w.writerow(["frame_idx", "latency_ms", "center_x", "center_y", "bbox_w", "bbox_h",
                    "mask_area", "nghi_doi_tuong"])
        for r in rows:
            w.writerow(["" if v is None else v for v in r])
    return p


class TestDocPhien:
    def test_thoi_diem_la_CONG_DON_latency(self, tmp_path):
        """`t_uoc_luong` phải cộng dồn `latency_ms`, KHÔNG chia đều (lệch 12 s trên phiên 98 s)."""
        d = L.doc_phien(_csv(tmp_path))
        assert [f["t_uoc_luong"] for f in d["frames"]] == [0.0, 0.3, 0.5, 1.0]
        assert d["tong_latency_s"] == pytest.approx(1.2)

    def test_bbox_dung_tu_tam_va_kich_thuoc(self, tmp_path):
        d = L.doc_phien(_csv(tmp_path))
        assert d["frames"][0]["bbox"] == [80, 70, 120, 130]
        assert d["frames"][3]["bbox"] is None, "ô rỗng (mất dấu) phải là None, không phải [0,0,0,0]"

    def test_ghi_lai_co_mask_bi_an(self, tmp_path):
        d = L.doc_phien(_csv(tmp_path))
        assert d["frames"][2]["may_an_mask"] is True
        assert d["frames"][0]["may_an_mask"] is False

    def test_khong_co_video_thi_video_none(self, tmp_path):
        d = L.doc_phien(_csv(tmp_path))
        assert d["video"] is None, "thiếu mp4 ⇒ None để UI báo, không im lặng phát file sai"


class TestGhiNhan:
    def test_append_only_va_co_provenance(self, tmp_path):
        p = tmp_path / "nhan"
        a = L.ghi_nhan("demoip_x", {"frame_vos": 5, "t_video": 1.5, "nhan": "dung"}, "Binh", p)
        b = L.ghi_nhan("demoip_x", {"frame_vos": 6, "t_video": 2.0, "nhan": "sai"}, "An", p)
        assert a["nguoi_gan"] == "Binh" and b["nguoi_gan"] == "An"
        for rec in (a, b):
            assert "do_luc" in rec and "git_rev" in rec, "thiếu provenance ⇒ không trích được"
        rows = L.doc_nhan("demoip_x", p)
        assert [r["frame_vos"] for r in rows] == [5, 6], "phải APPEND, không ghi đè"

    def test_nhan_la_bi_tu_choi(self, tmp_path):
        with pytest.raises(ValueError, match="nhãn không hợp lệ"):
            L.ghi_nhan("x", {"frame_vos": 1, "nhan": "chac_dung"}, "Binh", tmp_path)

    def test_thieu_nguoi_gan_bi_tu_choi(self, tmp_path):
        with pytest.raises(ValueError, match="nguoi_gan"):
            L.ghi_nhan("x", {"frame_vos": 1, "nhan": "dung"}, "  ", tmp_path)

    def test_bbox_dao_canh_bi_tu_choi(self, tmp_path):
        with pytest.raises(ValueError, match="bbox_dung"):
            L.ghi_nhan("x", {"frame_vos": 1, "nhan": "sai", "bbox_dung": [10, 10, 5, 5]}, "B", tmp_path)

    def test_bbox_hop_le_duoc_lam_tron(self, tmp_path):
        rec = L.ghi_nhan("x", {"frame_vos": 1, "nhan": "sai", "bbox_dung": [10.4, 20.6, 30.2, 40.9]},
                         "B", tmp_path)
        assert rec["bbox_dung"] == [10, 21, 30, 41]

    def test_dong_hong_khong_lam_sap_bo_nhan(self, tmp_path):
        p = tmp_path / "demoip_y.jsonl"
        p.write_text('{"frame_vos": 1, "nhan": "dung", "nguoi_gan": "A"}\n{hong\n', encoding="utf-8")
        rows = L.doc_nhan("demoip_y", tmp_path)
        assert len(rows) == 1, "dòng ghi dở phải bị bỏ qua, không ném"


class TestTongHop:
    def test_dem_theo_nguoi_va_muc_dong_y(self, tmp_path):
        p = tmp_path / "nhan"
        for nguoi, nhan, f in [("A", "dung", 1), ("A", "sai", 2), ("B", "dung", 1), ("B", "dung", 2)]:
            L.ghi_nhan("s", {"frame_vos": f, "t_video": f, "nhan": nhan}, nguoi, p)
        d = L.tong_hop("s", p)
        assert d["tong_nhan"] == 4 and d["so_nguoi"] == 2
        assert d["theo_nguoi"]["A"]["tong"] == 2
        # frame 1: A=dung, B=dung ⇒ đồng ý; frame 2: A=sai, B=dung ⇒ lệch
        assert d["dong_y_2_nguoi"] == {"so_frame_ca_hai": 2, "so_frame_dong_y": 1}

    def test_mot_nguoi_thi_khong_co_muc_dong_y(self, tmp_path):
        p = tmp_path / "nhan"
        L.ghi_nhan("s", {"frame_vos": 1, "nhan": "dung"}, "A", p)
        assert L.tong_hop("s", p)["dong_y_2_nguoi"] is None


class TestApiHttp:
    """Gọi HTTP thật (cổng 0) — bắt lỗi route/serialize mà test hàm thuần không thấy."""

    @pytest.fixture
    def may_chu(self, tmp_path, monkeypatch):
        monkeypatch.setattr(L, "THU_MUC_NHAN", tmp_path / "nhan")
        monkeypatch.setattr(L, "REPO_ROOT", tmp_path)
        (tmp_path / "data").mkdir()
        _csv(tmp_path / "data", ten="demoip_api")
        (tmp_path / "data" / "demoip_api_web.mp4").write_bytes(b"\x00" * 32)
        srv = L.tao_server(0, "Binh", "demoip_api")
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        yield f"http://127.0.0.1:{srv.server_address[1]}"
        srv.shutdown()
        srv.server_close()

    def test_trang_chu_va_sessions(self, may_chu):
        with urllib.request.urlopen(may_chu + "/") as r:
            assert b"G\xc3\xa1n nh\xc3\xa3n" in r.read()          # "Gán nhãn"
        d = json.load(urllib.request.urlopen(may_chu + "/api/sessions"))
        assert d["nguoi_gan"] == "Binh"
        assert [p["phien"] for p in d["phien"]] == ["demoip_api"]
        assert "dung" in d["nhan"]

    def test_frames_va_label(self, may_chu):
        d = json.load(urllib.request.urlopen(may_chu + "/api/frames?phien=demoip_api"))
        assert len(d["frames"]) == 4 and d["da_gan"] == []
        body = json.dumps({"phien": "demoip_api", "frame_vos": 2, "t_video": 0.5,
                           "nhan": "sai", "bbox_dung": [10, 10, 50, 50]}).encode()
        req = urllib.request.Request(may_chu + "/api/label", data=body,
                                     headers={"Content-Type": "application/json"})
        d = json.load(urllib.request.urlopen(req))
        assert d["ok"] and d["record"]["nguoi_gan"] == "Binh"
        assert d["tong_hop"]["theo_nguoi"]["Binh"]["sai"] == 1
        d2 = json.load(urllib.request.urlopen(may_chu + "/api/frames?phien=demoip_api"))
        assert len(d2["da_gan"]) == 1

    def test_nhan_sai_tra_400_chu_khong_500(self, may_chu):
        body = json.dumps({"phien": "demoip_api", "frame_vos": 1, "nhan": "bậy"}).encode()
        req = urllib.request.Request(may_chu + "/api/label", data=body,
                                     headers={"Content-Type": "application/json"})
        with pytest.raises(urllib.error.HTTPError) as e:
            urllib.request.urlopen(req)
        assert e.value.code == 400

    def test_video_co_Range(self, may_chu):
        """Chrome cần 206 + Content-Range để tua; thiếu thì `currentTime` không nhảy."""
        req = urllib.request.Request(may_chu + "/video?v=demoip_api_web.mp4",
                                     headers={"Range": "bytes=4-7"})
        with urllib.request.urlopen(req) as r:
            assert r.status == 206
            assert r.headers["Content-Range"] == "bytes 4-7/32"
            assert r.read() == b"\x00" * 4

    def test_body_qua_lon_tra_413(self, may_chu):
        """Nhãn chỉ vài trăm byte; `Content-Length` khổng lồ không được làm server cấp phát theo."""
        import http.client
        u = urllib.parse.urlparse(may_chu)
        c = http.client.HTTPConnection(u.hostname, u.port, timeout=10)
        c.putrequest("POST", "/api/label")
        c.putheader("Content-Type", "application/json")
        c.putheader("Content-Length", str(10 ** 8))
        c.endheaders()
        r = c.getresponse()
        assert r.status == 413, r.status
        c.close()

    def test_body_khong_phai_object_tra_400(self, may_chu):
        body = json.dumps(["dung"]).encode()
        req = urllib.request.Request(may_chu + "/api/label", data=body,
                                     headers={"Content-Type": "application/json"})
        with pytest.raises(urllib.error.HTTPError) as e:
            urllib.request.urlopen(req)
        assert e.value.code == 400

    def test_host_0_0_0_0_bind_duoc(self, tmp_path, monkeypatch):
        """Doc bảo 'mở http://<IP-WSL>:8770' khi không vào được 127.0.0.1 ⇒ server PHẢI bind 0.0.0.0."""
        monkeypatch.setattr(L, "THU_MUC_NHAN", tmp_path / "nhan")
        srv = L.tao_server(0, "B", None, host="0.0.0.0")
        try:
            assert srv.server_address[0] == "0.0.0.0"
        finally:
            srv.server_close()

    def test_ten_video_co_dau_gach_cheo_bi_chan(self, may_chu):
        req = urllib.request.Request(may_chu + "/video?v=../setup.py")
        with pytest.raises(urllib.error.HTTPError) as e:
            urllib.request.urlopen(req)
        assert e.value.code == 400


class TestChanDuongDan:
    """`POST /api/label` GHI file theo tên phiên ⇒ tên phiên là bề mặt ghi-ra-ngoài. Phải chặn."""

    @pytest.mark.parametrize("ten", ["../x", "../../etc/passwd", "a/b", "a\\b", "/abs", "C:\\x",
                                     "", "..", "a..b", "a b", "a%2fb"])
    def test_ten_xau_bi_tu_choi(self, ten):
        assert L.ten_hop_le(ten) is False

    @pytest.mark.parametrize("ten", ["demoip_1125-121456", "fast_1101-155053", "a.b_c-d"])
    def test_ten_that_duoc_chap_nhan(self, ten):
        assert L.ten_hop_le(ten) is True

    def test_ghi_nhan_ten_xau_khong_tao_file(self, tmp_path):
        with pytest.raises(ValueError, match="không hợp lệ"):
            L.ghi_nhan("../thoat", {"frame_vos": 1, "nhan": "dung"}, "B", tmp_path)
        assert list(tmp_path.rglob("*.jsonl")) == [], "không được tạo file nào khi tên bẩn"

    def test_api_label_ten_xau_tra_400(self, tmp_path, monkeypatch):
        monkeypatch.setattr(L, "THU_MUC_NHAN", tmp_path / "nhan")
        srv = L.tao_server(0, "B", None)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            body = json.dumps({"phien": "../../thoat", "frame_vos": 1, "nhan": "dung"}).encode()
            req = urllib.request.Request(f"http://127.0.0.1:{srv.server_address[1]}/api/label",
                                         data=body, headers={"Content-Type": "application/json"})
            with pytest.raises(urllib.error.HTTPError) as e:
                urllib.request.urlopen(req)
            assert e.value.code == 400
            assert not (tmp_path / "thoat.jsonl").exists()
            assert not (tmp_path / "nhan.jsonl").exists()
        finally:
            srv.shutdown()
            srv.server_close()


class TestTongHopCLI:
    """`--tong-hop` phải chạy được khi thư mục nhãn NGOÀI repo (`LABELUI_NHAN_DIR=/tmp/...`).

    Đã gặp thật: bản đầu in `out.relative_to(REPO_ROOT)` ⇒ ValueError NGAY SAU KHI ghi xong artifact,
    tức file đúng nhưng lệnh thoát mã 1 (script tự động sẽ hiểu là hỏng).
    """

    def test_chay_duoc_voi_thu_muc_ngoai_repo(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setattr(L, "THU_MUC_NHAN", tmp_path / "ngoai")
        L.ghi_nhan("demoip_x", {"frame_vos": 1, "t_video": 0.3, "nhan": "dung"}, "Binh")
        L.ghi_nhan("demoip_x", {"frame_vos": 1, "t_video": 0.3, "nhan": "dung"}, "An")
        csv = _csv(tmp_path, ten="demoip_x")
        ma = L.main(["--tong-hop", str(csv)])
        out = capsys.readouterr().out
        assert ma == 0, out
        assert "dong_y_2_nguoi" in out
        assert (tmp_path / "ngoai" / "demoip_x_tonghop.json").is_file()

    def test_duong_dan_gon_khong_nem(self, tmp_path, monkeypatch):
        monkeypatch.setattr(L, "REPO_ROOT", tmp_path)
        assert L.duong_dan_gon(tmp_path / "a") == "a"                    # trong repo → gọn
        assert L.duong_dan_gon(Path("/tmp/khac/a")) == "/tmp/khac/a"      # ngoài repo → nguyên gốc


class TestHangSoVaTaiLieu:
    def test_moi_nhan_deu_co_mo_ta(self):
        for k, mo_ta in L.NHAN.items():
            assert len(mo_ta) > 15, f"nhãn `{k}` phải có mô tả đọc được cho người dán"

    def test_huong_dan_ton_tai_va_neu_ca_bay(self):
        p = REPO / "docs" / "cach-gan-nhan.md"
        assert p.is_file(), "phải có hướng dẫn gán nhãn cho người dùng"
        s = p.read_text(encoding="utf-8")
        assert "latency_ms" in s, "hướng dẫn phải nói về cộng dồn latency_ms"
        assert "2 người" in s or "người thứ 2" in s
        assert "hệ số bù" in s, "phải nói về hệ số bù (không bù thì cuối video lệch ~3 s)"
        assert "lệch" in s, "phải cảnh báo người dán khi đứng giữa 2 bước"
        assert "--host" in s, "hướng dẫn mở từ Windows phải khớp cờ THẬT của tool (--host 0.0.0.0)"
