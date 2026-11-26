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

    def test_bbox_rong_bi_tu_choi(self, tmp_path):
        """`bbox_dung: []` từng LỌT kiểm (độ dài nằm trong nhánh `is not None`) ⇒ ghi nhãn rác."""
        with pytest.raises(ValueError, match="bbox_dung"):
            L.ghi_nhan("x", {"frame_vos": 1, "nhan": "sai", "bbox_dung": []}, "B", tmp_path)

    def test_bbox_phan_tu_khong_phai_so(self, tmp_path):
        for xau in ([None] * 4, [{}, 1, 2, 3], ["a", "b", "c", "d"]):
            with pytest.raises(ValueError, match="bbox_dung"):
                L.ghi_nhan("x", {"frame_vos": 1, "nhan": "sai", "bbox_dung": xau}, "B", tmp_path)

    def test_thieu_frame_vos_bi_tu_choi(self, tmp_path):
        with pytest.raises(ValueError, match="frame_vos"):
            L.ghi_nhan("x", {"nhan": "dung"}, "B", tmp_path)

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
        dy = d["dong_y_2_nguoi"]
        assert (dy["so_buoc_ca_hai"], dy["so_buoc_ca_hai_co_ket_luan"], dy["so_buoc_dong_y"]) == (2, 2, 1)
        # in TÊN HIỂN THỊ ("A","B"), không in khoá casefold ("a","b") — review vòng 4, P3-17
        assert dy["theo_cap"] == [{"cap": ["A", "B"], "so_buoc_ca_hai_co_ket_luan": 2,
                                   "so_buoc_dong_y": 1}]

    def test_BO_QUA_khong_duoc_tinh_la_dong_y(self, tmp_path):
        """Hai người cùng bấm `0` = "không kết luận được" ⇒ KHÔNG phải "2 người đồng ý" (review vòng 2)."""
        p = tmp_path / "nhan"
        for nguoi in ("A", "B"):
            L.ghi_nhan("s", {"buoc": 1, "frame_vos": 1, "nhan": "bo_qua"}, nguoi, p)
            L.ghi_nhan("s", {"buoc": 2, "frame_vos": 2, "nhan": "dung"}, nguoi, p)
        d = L.tong_hop("s", p)["dong_y_2_nguoi"]
        assert (d["so_buoc_ca_hai"], d["so_buoc_ca_hai_co_ket_luan"], d["so_buoc_dong_y"]) == (2, 1, 1)

    def test_nhan_CUOI_cua_mot_nguoi_la_nhan_hieu_luc(self, tmp_path):
        """Bấm `2` rồi `s` (mặc định ĐÚNG) từng tạo 2 nhãn mâu thuẫn: đếm mọi dòng thì `theo_nguoi` và
        `dong_y_2_nguoi` nói về hai tập khác nhau. Nhãn cuối mới có hiệu lực."""
        p = tmp_path / "nhan"
        L.ghi_nhan("s", {"frame_vos": 1, "nhan": "sai"}, "A", p)
        L.ghi_nhan("s", {"frame_vos": 1, "nhan": "dung"}, "A", p)     # người này đổi ý
        L.ghi_nhan("s", {"frame_vos": 1, "nhan": "dung"}, "B", p)
        d = L.tong_hop("s", p)
        assert d["theo_nguoi"]["A"]["dung"] == 1 and d["theo_nguoi"]["A"]["sai"] == 0
        assert d["theo_nguoi"]["A"]["tong"] == 1, "một bước chỉ đếm 1 lần cho mỗi người"
        assert d["so_nhan_trung"] == 1 and d["so_buoc_da_dan"] == 1
        dy = d["dong_y_2_nguoi"]
        assert (dy["so_buoc_ca_hai"], dy["so_buoc_ca_hai_co_ket_luan"], dy["so_buoc_dong_y"]) == (1, 1, 1)

    def test_mot_nguoi_thi_khong_co_muc_dong_y(self, tmp_path):
        p = tmp_path / "nhan"
        L.ghi_nhan("s", {"frame_vos": 1, "nhan": "dung"}, "A", p)
        assert L.tong_hop("s", p)["dong_y_2_nguoi"] is None


class TestApiHttp:
    """Gọi HTTP thật (cổng 0) — bắt lỗi route/serialize mà test hàm thuần không thấy."""

    @pytest.fixture
    def may_chu(self, tmp_path, monkeypatch):
        (tmp_path / "data").mkdir()
        monkeypatch.setattr(L, "DATA_DIR", tmp_path / "data")
        monkeypatch.setattr(L, "THU_MUC_NHAN", tmp_path / "data" / "nhan")
        monkeypatch.setattr(L, "REPO_ROOT", tmp_path)
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
        body = json.dumps({"phien": "demoip_api", "buoc": 2, "frame_vos": 2, "t_video": 0.5,
                           "nhan": "sai", "bbox_dung": [10, 10, 50, 50],
                           "nguoi_gan": "Binh"}).encode()
        req = urllib.request.Request(may_chu + "/api/label", data=body,
                                     headers={"Content-Type": "application/json"})
        d = json.load(urllib.request.urlopen(req))
        assert d["ok"] and d["record"]["nguoi_gan"] == "Binh"
        assert d["tong_hop"]["theo_nguoi"]["Binh"]["sai"] == 1
        # `/api/frames` KHÔNG có `nguoi` ⇒ KHÔNG trả nhãn của ai (bản cũ fallback về `--nguoi-gan` ⇒
        # người thứ 2 thấy đúng nhãn của người thứ 1 — review vòng 4, P1-1)
        d2 = json.load(urllib.request.urlopen(may_chu + "/api/frames?phien=demoip_api"))
        assert d2["da_gan"] == [] and d2["nguoi_dang_dan"] is None
        d3 = json.load(urllib.request.urlopen(may_chu + "/api/frames?phien=demoip_api&nguoi=Binh"))
        assert len(d3["da_gan"]) == 1
        d4 = json.load(urllib.request.urlopen(may_chu + "/api/frames?phien=demoip_api&nguoi=binh"))
        assert len(d4["da_gan"]) == 1, "lọc theo KHOÁ tên (NFC+casefold), không so chuỗi thô"

    def test_nhan_sai_tra_400_chu_khong_500(self, may_chu):
        body = json.dumps({"phien": "demoip_api", "buoc": 1, "frame_vos": 1, "nhan": "bậy",
                           "nguoi_gan": "Binh"}).encode()
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

    def test_content_type_sai_tra_415(self, may_chu):
        """Request "simple" (text/plain, no-cors) phải bị chặn — nếu không, trang web khác chèn được
        nhãn vào file bằng chứng dưới TÊN người đang dán."""
        body = json.dumps({"phien": "demoip_api", "buoc": 1, "frame_vos": 1, "nhan": "dung",
                           "nguoi_gan": "Binh"}).encode()
        req = urllib.request.Request(may_chu + "/api/label", data=body,
                                     headers={"Content-Type": "text/plain"})
        with pytest.raises(urllib.error.HTTPError) as e:
            urllib.request.urlopen(req)
        assert e.value.code == 415

    def test_thieu_nguoi_gan_trong_body_tra_400(self, may_chu):
        """Ô 'Người gán' trống KHÔNG được lấy `--nguoi-gan` thay thế (nếu không, người thứ 2 xoá ô tên
        là nhãn của họ ghi dưới tên người thứ 1 — review vòng 4, P1-1)."""
        body = json.dumps({"phien": "demoip_api", "buoc": 0, "frame_vos": 0, "nhan": "dung",
                           "nguoi_gan": "   "}).encode()
        req = urllib.request.Request(may_chu + "/api/label", data=body,
                                     headers={"Content-Type": "application/json"})
        with pytest.raises(urllib.error.HTTPError) as e:
            urllib.request.urlopen(req)
        assert e.value.code == 400

    def test_ten_nguoi_dan_lay_tu_BODY_khong_phai_co_CLI(self, may_chu):
        """P1-A: server chạy `--nguoi-gan Binh` nhưng nhãn gửi `nguoi_gan: "An"` ⇒ file phải ghi "An".
        Trước đây luôn ghi `self.nguoi_gan` ⇒ 2 người dùng chung 1 server ra `so_nguoi = 1`."""
        body = json.dumps({"phien": "demoip_api", "buoc": 0, "frame_vos": 0, "nhan": "dung",
                           "nguoi_gan": "An"}).encode()
        req = urllib.request.Request(may_chu + "/api/label", data=body,
                                     headers={"Content-Type": "application/json"})
        d = json.load(urllib.request.urlopen(req))
        assert d["record"]["nguoi_gan"] == "An", "phải ghi tên trong BODY, không phải cờ --nguoi-gan"
        assert d["tong_hop"]["theo_nguoi"]["An"]["dung"] == 1
        assert "Binh" not in d["tong_hop"]["theo_nguoi"], "Binh chưa dán gì"

    def test_buoc_ngoai_dai_bi_tu_choi(self, may_chu):
        """P2-5: `buoc` phải nằm trong CSV server đang giữ — không thì file bằng chứng nhận bước ma."""
        body = json.dumps({"phien": "demoip_api", "buoc": 9999, "frame_vos": 0, "nhan": "dung",
                           "nguoi_gan": "Binh"}).encode()
        req = urllib.request.Request(may_chu + "/api/label", data=body,
                                     headers={"Content-Type": "application/json"})
        with pytest.raises(urllib.error.HTTPError) as e:
            urllib.request.urlopen(req)
        assert e.value.code == 400

    def test_frame_vos_khong_khop_buoc_bi_tu_choi(self, may_chu):
        body = json.dumps({"phien": "demoip_api", "buoc": 0, "frame_vos": 123, "nhan": "dung",
                           "nguoi_gan": "Binh"}).encode()
        req = urllib.request.Request(may_chu + "/api/label", data=body,
                                     headers={"Content-Type": "application/json"})
        with pytest.raises(urllib.error.HTTPError) as e:
            urllib.request.urlopen(req)
        assert e.value.code == 400

    def test_host_la_tra_403(self, may_chu):
        """DNS rebinding: Origin == Host nên chỉ kiểm Origin là vô ích; phải allowlist `Host`."""
        body = json.dumps({"phien": "demoip_api", "buoc": 0, "nhan": "dung"}).encode()
        req = urllib.request.Request(may_chu + "/api/label", data=body,
                                     headers={"Content-Type": "application/json",
                                              "Host": "evil.example.com"})
        with pytest.raises(urllib.error.HTTPError) as e:
            urllib.request.urlopen(req)
        assert e.value.code == 403

    def test_host_la_IP_LAN_cua_may_duoc_nhan(self, may_chu):
        """`docs/cach-gan-nhan.md` §5 hướng dẫn `--host 0.0.0.0` rồi mở `http://<IP-WSL>:8770`.

        Allowlist chỉ so `gethostbyname` (MỘT địa chỉ) từng làm mọi POST 403 trên đường dự phòng đó
        trong khi trang + video vẫn chạy (review vòng 3, P2-7). Test này POST thật bằng `Host: <IP>:port`.
        """
        import socket
        ips = sorted(L._Handler.ip_may() - {"127.0.0.1"})
        if not ips:
            pytest.skip("máy chỉ có 127.0.0.1 — không có IP LAN để thử")
        port = may_chu.rsplit(":", 1)[1]
        body = json.dumps({"phien": "demoip_api", "buoc": 0, "frame_vos": 0, "nhan": "dung",
                           "nguoi_gan": "Binh"}).encode()
        req = urllib.request.Request(may_chu + "/api/label", data=body,
                                     headers={"Content-Type": "application/json",
                                              "Host": f"{ips[0]}:{port}"})
        assert json.load(urllib.request.urlopen(req))["ok"] is True
        assert socket.inet_aton(ips[0])            # đúng là IPv4 thật của máy này

    def test_frames_loc_theo_ten_nguoi_hoi(self, may_chu):
        L.ghi_nhan("demoip_api", {"buoc": 1, "frame_vos": 1, "nhan": "sai"}, "An")
        L.ghi_nhan("demoip_api", {"buoc": 2, "frame_vos": 2, "nhan": "dung"}, "Binh")
        d = json.load(urllib.request.urlopen(may_chu + "/api/frames?phien=demoip_api&nguoi=An"))
        assert [r["buoc"] for r in d["da_gan"]] == [1] and d["nguoi_dang_dan"] == "An"
        assert d["so_nhan_nguoi_khac"] == 1

    def test_origin_la_tra_403(self, may_chu):
        body = json.dumps({"phien": "demoip_api", "buoc": 1, "frame_vos": 1, "nhan": "dung",
                           "nguoi_gan": "Binh"}).encode()
        req = urllib.request.Request(may_chu + "/api/label", data=body,
                                     headers={"Content-Type": "application/json",
                                              "Origin": "https://evil.example"})
        with pytest.raises(urllib.error.HTTPError) as e:
            urllib.request.urlopen(req)
        assert e.value.code == 403

    def test_origin_cung_goc_duoc_nhan(self, may_chu):
        body = json.dumps({"phien": "demoip_api", "buoc": 1, "frame_vos": 1, "nhan": "dung",
                           "nguoi_gan": "Binh"}).encode()
        host = urllib.parse.urlparse(may_chu).netloc
        req = urllib.request.Request(may_chu + "/api/label", data=body,
                                     headers={"Content-Type": "application/json",
                                              "Origin": f"http://{host}"})
        assert json.load(urllib.request.urlopen(req))["ok"] is True

    def test_t_video_kieu_la_tra_400(self, may_chu):
        """`t_video: [1]`/`1e400` (json nhận Infinity) từng làm server 500 — phải là 400."""
        for gia in ([1], 1e400):
            body = json.dumps({"phien": "demoip_api", "buoc": 0, "frame_vos": 0, "nhan": "dung",
                               "nguoi_gan": "Binh", "t_video": gia}).encode()
            req = urllib.request.Request(may_chu + "/api/label", data=body,
                                         headers={"Content-Type": "application/json"})
            with pytest.raises(urllib.error.HTTPError) as e:
                urllib.request.urlopen(req)
            assert e.value.code == 400, gia

    def test_thieu_frame_vos_tra_400(self, may_chu):
        body = json.dumps({"phien": "demoip_api", "buoc": 0, "nhan": "dung",
                           "nguoi_gan": "Binh"}).encode()
        req = urllib.request.Request(may_chu + "/api/label", data=body,
                                     headers={"Content-Type": "application/json"})
        with pytest.raises(urllib.error.HTTPError) as e:
            urllib.request.urlopen(req)
        assert e.value.code == 400

    def test_NaN_trong_csv_khong_lam_hong_JSON(self, tmp_path, monkeypatch):
        """`json.dumps` mặc định in `NaN`/`Infinity` — KHÔNG phải JSON, Chrome `JSON.parse` ném ⇒ cả UI
        chết. `/api/frames` phải trả `null` cho số méo (review vòng 5, P3-B)."""
        (tmp_path / "data").mkdir(exist_ok=True)
        csv = tmp_path / "data" / "nan_metrics.csv"
        csv.write_text("frame_idx,latency_ms,center_x,center_y,bbox_w,bbox_h,mask_area\n"
                       "0,NaN,10,10,4,4,Infinity\n", encoding="utf-8")
        monkeypatch.setattr(L, "DATA_DIR", tmp_path / "data")
        monkeypatch.setattr(L, "THU_MUC_NHAN", tmp_path / "data" / "nhan")
        srv = L.tao_server(0, "B", None)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            raw = urllib.request.urlopen(
                f"http://127.0.0.1:{srv.server_address[1]}/api/frames?phien=nan").read()
            # chỉ kiểm GIÁ TRỊ (tên test chứa chữ "NaN" nên không so cả payload)
            assert b": NaN" not in raw and b": Infinity" not in raw
            assert b": -Infinity" not in raw
            json.loads(raw)                       # parser strict: phải đọc được
        finally:
            srv.shutdown()
            srv.server_close()

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

    def test_range_suffix_va_ngoai_bien(self, may_chu):
        """`bytes=-8` là SUFFIX (8 byte cuối), không phải start=0; start vượt độ dài ⇒ 416."""
        req = urllib.request.Request(may_chu + "/video?v=demoip_api_web.mp4",
                                     headers={"Range": "bytes=-8"})
        with urllib.request.urlopen(req) as r:
            assert r.status == 206
            assert r.headers["Content-Range"] == "bytes 24-31/32"
        req = urllib.request.Request(may_chu + "/video?v=demoip_api_web.mp4",
                                     headers={"Range": "bytes=100-200"})
        with pytest.raises(urllib.error.HTTPError) as e:
            urllib.request.urlopen(req)
        assert e.value.code == 416

    def test_nhan_nguoi_khac_chi_tra_SO_LUONG(self, may_chu):
        """Độc lập phải do SERVER bảo đảm: trả nội dung nhãn người khác rồi ẩn bằng CSS là giả.

        Bản cũ để nhãn DUY NHẤT thuộc `An` nên `da_gan == []` xanh cả khi server fallback về
        `--nguoi-gan` (tức assertion không phân biệt được gì). Nay mỗi người có nhãn riêng.
        """
        L.ghi_nhan("demoip_api", {"buoc": 9, "frame_vos": 9, "t_video": 3.0, "nhan": "sai"}, "An")
        L.ghi_nhan("demoip_api", {"buoc": 8, "frame_vos": 8, "t_video": 2.0, "nhan": "dung"}, "Binh")
        d = json.load(urllib.request.urlopen(may_chu + "/api/frames?phien=demoip_api&nguoi=Binh"))
        assert [r["buoc"] for r in d["da_gan"]] == [8], "chỉ nhãn CỦA MÌNH, không lẫn của An"
        assert d["so_nhan_nguoi_khac"] == 1 and d["nguoi_khac"] == ["An"]
        assert "An" not in json.dumps([r["nguoi_gan"] for r in d["da_gan"]])

    def test_ten_video_co_dau_gach_cheo_bi_chan(self, may_chu):
        req = urllib.request.Request(may_chu + "/video?v=../setup.py")
        with pytest.raises(urllib.error.HTTPError) as e:
            urllib.request.urlopen(req)
        assert e.value.code == 400


class TestCsvBan:
    """CSV bẩn phải bị TỪ CHỐI, không được lặng lẽ dồn nhãn vào bước 0 (review độc lập P2-4)."""

    def test_BOM_khong_lam_mat_frame_idx(self, tmp_path):
        p = tmp_path / "bom_metrics.csv"
        p.write_text("\ufeffframe_idx,latency_ms,center_x,center_y,bbox_w,bbox_h,mask_area\n"
                     "0,100,10,10,4,4,9\n1,100,10,10,4,4,9\n", encoding="utf-8")
        d = L.doc_phien(p)
        assert [f["frame_vos"] for f in d["frames"]] == [0, 1], "BOM từng làm mọi frame_vos = 0"

    def test_thieu_cot_frame_idx_bi_tu_choi(self, tmp_path):
        p = tmp_path / "thieu_metrics.csv"
        p.write_text("latency_ms,mask_area\n100,9\n", encoding="utf-8")
        with pytest.raises(ValueError, match="frame_idx"):
            L.doc_phien(p)

    def test_frame_idx_lap_thi_CANH_BAO_chu_khong_tu_choi(self, tmp_path):
        """`frame_idx` lặp là HỢP LỆ (nguồn file lặp quay về 0; `data/gpu_metrics.csv` có 50 dòng lặp).
        Từ chối là chặn phiên thật ⇒ chỉ cảnh báo, và `buoc` (số thứ tự dòng) là danh tính của bước."""
        p = tmp_path / "lap_metrics.csv"
        p.write_text("frame_idx,latency_ms\n5,100\n3,100\n3,100\n", encoding="utf-8")
        d = L.doc_phien(p)
        assert [f["buoc"] for f in d["frames"]] == [0, 1, 2]
        assert [f["frame_vos"] for f in d["frames"]] == [5, 3, 3]
        assert d["canh_bao"] and "lặp" in d["canh_bao"]

    def test_hai_buoc_cung_frame_vos_van_la_hai_buoc(self, tmp_path):
        """Nếu khoá theo `frame_vos` thì hai bước khác nhau bị GỘP ⇒ mất dữ liệu của một bước."""
        p = tmp_path / "nhau"
        L.ghi_nhan("s", {"buoc": 0, "frame_vos": 7, "nhan": "dung"}, "A", p)
        L.ghi_nhan("s", {"buoc": 1, "frame_vos": 7, "nhan": "sai"}, "A", p)
        d = L.tong_hop("s", p)
        assert d["so_buoc_da_dan"] == 2, "hai dòng CSV khác nhau phải là hai bước"
        assert d["theo_nguoi"]["A"]["tong"] == 2

    def test_duong_dan_tuong_doi_khong_lam_sap(self, tmp_path, monkeypatch):
        """`csv_path.relative_to(REPO_ROOT)` từng NÉM khi truyền đường dẫn tương đối (CLI/thư viện)."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / "rel_metrics.csv").write_text("frame_idx,latency_ms\n0,100\n", encoding="utf-8")
        d = L.doc_phien(Path("rel_metrics.csv"))
        assert d["frames"][0]["buoc"] == 0

    def test_csv_rong_bi_tu_choi(self, tmp_path):
        p = tmp_path / "rong_metrics.csv"
        p.write_text("frame_idx,latency_ms\n", encoding="utf-8")
        with pytest.raises(ValueError, match="rỗng"):
            L.doc_phien(p)


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


class TestGopTenNguoi:
    """`Binh` / `binh` / `Bình` phải là MỘT người — nếu không, một người gõ lại tên với chữ hoa khác
    sẽ tạo ra "2 người đồng ý" giả và `--tong-hop` thoát mã 0 (review vòng 3, P2-8)."""

    def test_case_va_dau_khong_tao_them_nguoi(self, tmp_path):
        p = tmp_path / "nhan"
        for ten in ("Binh", "binh", "BINH"):
            L.ghi_nhan("s", {"buoc": 1, "frame_vos": 1, "nhan": "dung"}, ten, p)
        d = L.tong_hop("s", p)
        assert d["so_nguoi"] == 1, "cùng một người gõ 3 kiểu phải là 1"
        assert d["theo_nguoi"]["Binh"]["tong"] == 1, "in theo tên hiển thị đầu tiên, không in khoá"
        # thứ tự gặp trong file (append-only), không phải sorted — để người đọc thấy diễn biến
        assert sorted(d["ten_theo_nguoi"]["binh"]["ten"]) == ["BINH", "Binh", "binh"]
        assert d["ten_theo_nguoi"]["binh"]["nhan_dau"] and d["ten_theo_nguoi"]["binh"]["nhan_cuoi"]

    def test_khoa_nguoi_bi_sua_tay_khong_tach_1_nguoi_thanh_2(self, tmp_path):
        """Tin `khoa_nguoi` đã lưu thì một dòng sửa tay (hoặc của bản tool khác) tách 1 người thành 2
        ⇒ `so_nguoi = 2` giả + cặp "tự đồng ý với mình" (review vòng 4, P3-17)."""
        p = tmp_path / "nhau"
        p.mkdir()
        (p / "s.jsonl").write_text(
            '{"buoc": 1, "frame_vos": 1, "nhan": "dung", "nguoi_gan": "Binh", "khoa_nguoi": "binh"}\n'
            '{"buoc": 2, "frame_vos": 2, "nhan": "dung", "nguoi_gan": "Binh", "khoa_nguoi": "BINH-2"}\n',
            encoding="utf-8")
        d = L.tong_hop("s", p)
        assert d["so_nguoi"] == 1, "phải tính lại khoá từ tên, không tin trường đã lưu"

    def test_ba_nguoi_co_dong_y_theo_cap(self, tmp_path):
        p = tmp_path / "nhan"
        for nguoi, nhan in [("A", "dung"), ("B", "dung"), ("C", "sai")]:
            L.ghi_nhan("s", {"buoc": 1, "frame_vos": 1, "nhan": nhan}, nguoi, p)
        dy = L.tong_hop("s", p)["dong_y_2_nguoi"]
        assert dy["so_buoc_dong_y"] == 0, "TẤT CẢ đồng ý = 0 (C nói sai)"
        cap = {tuple(x["cap"]): x["so_buoc_dong_y"] for x in dy["theo_cap"]}
        assert cap == {("A", "B"): 1, ("A", "C"): 0, ("B", "C"): 0}


class TestTenNguoiDan:
    @pytest.mark.parametrize("ten", ["", "  ", "?", None])
    def test_ten_khong_dung_duoc(self, ten):
        with pytest.raises(ValueError):
            L.chuan_hoa_ten(ten)

    def test_ten_qua_dai(self):
        with pytest.raises(ValueError, match="quá dài"):
            L.chuan_hoa_ten("x" * 41)

    def test_ten_hop_le(self):
        assert L.chuan_hoa_ten("  Nguyễn An Bình  ") == "Nguyễn An Bình"


class TestCacheVaTen:
    def test_cache_tra_ve_cung_ket_qua_va_doi_khi_file_doi(self, tmp_path):
        p = _csv(tmp_path, ten="c")
        a = L.doc_phien_cached(p)
        b = L.doc_phien_cached(p)
        assert a is b, "lần 2 phải lấy từ cache (nếu không: parse CSV ở MỌI lần bấm phím)"
        p.write_text(p.read_text(encoding="utf-8").replace("0,300", "0,999"), encoding="utf-8")
        c = L.doc_phien_cached(p)
        assert c is not a and c["frames"][0]["latency_ms"] == 999.0, \
            "CSV bị ghi lại thì cache phải bỏ (mtime/size đổi)"

    def test_ten_co_ky_tu_dieu_khien_bi_tu_choi(self):
        for ten in ("An\nBinh", "An\tBinh", "An\x00"):
            with pytest.raises(ValueError, match="điều khiển"):
                L.chuan_hoa_ten(ten)


class TestDongRac:
    def test_dong_json_khong_phai_nhan_khong_lam_sap_tong_hop(self, tmp_path):
        """`tong_hop` chạy TRONG response của mỗi POST ⇒ một dòng rác làm nó ném là nhãn đã ghi xong
        nhưng UI báo lỗi (review vòng 2, P2-3)."""
        p = tmp_path / "nhau"
        p.mkdir()
        (p / "s.jsonl").write_text(
            '{"buoc": 1, "frame_vos": 1, "nhan": "dung", "nguoi_gan": "A"}\n'
            '123\n'
            '"x"\n'
            '{"nhan": "dung"}\n'
            '{"buoc": 2, "nhan": "khong_co_nhan_nay", "nguoi_gan": "A"}\n', encoding="utf-8")
        d = L.tong_hop("s", p)
        # 4 dòng rác: số, chuỗi, thiếu `nguoi_gan`, nhãn không có trong tập đóng
        assert d["so_nhan_hieu_luc"] == 1 and d["so_nhan_loi"] == 4
        assert d["so_nhan_trung"] == 0, "dòng rác không được tính là 'dán trùng'"


class TestLietKePhien:
    def test_ten_file_la_bi_BO_QUA_khong_nem(self, tmp_path, monkeypatch):
        """File CSV tên lạ (dấu tiếng Việt, bắt đầu bằng `.`) từng làm `/api/sessions` 500 ⇒ cả tool
        không mở được. Đường liệt kê phải bỏ qua, không ném."""
        monkeypatch.setattr(L, "DATA_DIR", tmp_path)
        monkeypatch.setattr(L, "THU_MUC_NHAN", tmp_path / "nhan")
        for ten in ("hợp_lệ_metrics.csv", ".an_metrics.csv"):
            (tmp_path / ten).write_text("frame_idx,latency_ms\n0,100\n", encoding="utf-8")
            (tmp_path / ten.replace("_metrics.csv", "_web.mp4")).write_bytes(b"x")
        (tmp_path / "ok_metrics.csv").write_text("frame_idx,latency_ms\n0,100\n", encoding="utf-8")
        (tmp_path / "ok_web.mp4").write_bytes(b"x")
        assert [p["phien"] for p in L.liet_ke_phien()] == ["ok"]

    def test_doc_chua_xac_minh_n_tu_run_info(self, tmp_path, monkeypatch):
        monkeypatch.setattr(L, "DATA_DIR", tmp_path)
        monkeypatch.setattr(L, "THU_MUC_NHAN", tmp_path / "nhan")
        (tmp_path / "a_metrics.csv").write_text("frame_idx,latency_ms\n0,100\n", encoding="utf-8")
        (tmp_path / "a_web.mp4").write_bytes(b"x")
        (tmp_path / "a_run_info.json").write_text('{"chua_xac_minh_n": 49}', encoding="utf-8")
        assert L.liet_ke_phien()[0]["chua_xac_minh_n"] == 49

    def test_thieu_run_info_thi_none(self, tmp_path, monkeypatch):
        monkeypatch.setattr(L, "DATA_DIR", tmp_path)
        monkeypatch.setattr(L, "THU_MUC_NHAN", tmp_path / "nhan")
        (tmp_path / "b_metrics.csv").write_text("frame_idx,latency_ms\n0,100\n", encoding="utf-8")
        (tmp_path / "b_web.mp4").write_bytes(b"x")
        assert L.liet_ke_phien()[0]["chua_xac_minh_n"] is None


class TestTongHopCLI:
    def test_phien_nhan_ten_CSV_duoc_chuan_hoa(self, tmp_path, monkeypatch):
        """Doc hứa `--phien` nhận `…_metrics.csv`; code cũ so tên trần nên đưa tên CSV vào là không
        chọn gì. Nay chuẩn hoá trước khi so."""
        monkeypatch.setattr(L, "THU_MUC_NHAN", tmp_path / "nhan")
        seen = {}

        def gia(port, nguoi, phien=None, host="127.0.0.1"):
            seen["phien"] = phien
            raise SystemExit(0)

        monkeypatch.setattr(L, "tao_server", gia)
        with pytest.raises(SystemExit):
            L.main(["--nguoi-gan", "B", "--phien", "data/demoip_x_metrics.csv"])
        assert seen["phien"] == "demoip_x"

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

    @pytest.mark.parametrize("so_nguoi, mong_doi", [(1, 1), (2, 0)])
    def test_chi_MOT_nguoi_thi_exit_1(self, tmp_path, monkeypatch, capsys, so_nguoi, mong_doi):
        """Cổng quan trọng nhất của `--tong-hop` (một người ⇒ chưa trích được) từng KHÔNG có test
        đường thất bại ⇒ xoá cả cổng mà suite vẫn xanh (review vòng 4, P2-6)."""
        monkeypatch.setattr(L, "THU_MUC_NHAN", tmp_path / "nhan")
        csv = _csv(tmp_path, ten="demoip_x")
        for i, nguoi in enumerate(["Binh", "An"][:so_nguoi]):
            for buoc in (0, 1):
                L.ghi_nhan("demoip_x", {"buoc": buoc, "frame_vos": buoc, "nhan": "dung"}, nguoi)
        ma = L.main(["--tong-hop", str(csv)])
        out = capsys.readouterr().out
        assert ma == mong_doi, out
        art = json.loads((tmp_path / "nhan" / "demoip_x_tonghop.json").read_text(encoding="utf-8"))
        assert art["ket_qua"] is (mong_doi == 0), "artifact phải nói rõ lần chạy này có trích được không"

    def test_buoc_ngoai_dai_thi_exit_1(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setattr(L, "THU_MUC_NHAN", tmp_path / "nhan")
        csv = _csv(tmp_path, ten="demoip_x")            # CSV 4 bước
        for nguoi in ("Binh", "An"):
            L.ghi_nhan("demoip_x", {"buoc": 99, "frame_vos": 99, "nhan": "dung"}, nguoi)
        assert L.main(["--tong-hop", str(csv)]) == 1
        assert "NGOÀI dải" in capsys.readouterr().out

    def test_thieu_CSV_thi_artifact_ghi_kiem_dai_buoc_false(self, tmp_path, monkeypatch, capsys):
        """Chạy trên clone sạch: nhãn được track còn CSV thì không ⇒ cổng dải `buoc` KHÔNG chạy. Artifact
        phải nói rõ, không được trông y như đã kiểm (review vòng 5, P2-A)."""
        monkeypatch.setattr(L, "THU_MUC_NHAN", tmp_path / "nhan")
        for nguoi in ("Binh", "An"):
            L.ghi_nhan("khong_co_csv", {"buoc": 0, "frame_vos": 0, "nhan": "dung"}, nguoi)
        ma = L.main(["--tong-hop", str(tmp_path / "khong_co_csv_metrics.csv")])   # file KHÔNG tồn tại
        out = capsys.readouterr().out
        art = json.loads((tmp_path / "nhan" / "khong_co_csv_tonghop.json").read_text(encoding="utf-8"))
        assert ma == 0, out
        assert art["kiem_dai_buoc"] is False and art["ket_qua"] is True
        assert "KHÔNG kiểm được" in out

    def test_khong_co_nhan_hop_le_thi_exit_1_va_artifact_false(self, tmp_path, monkeypatch, capsys):
        """Cổng sớm nhất (0 nhãn hợp lệ) từng KHÔNG có test và KHÔNG ghi artifact ⇒ một file
        `ket_qua=true` cũ còn nguyên trên đĩa (review vòng 5, P3)."""
        monkeypatch.setattr(L, "THU_MUC_NHAN", tmp_path / "nhan")
        (tmp_path / "nhan").mkdir()
        (tmp_path / "nhan" / "rong.jsonl").write_text('123\n"x"\n', encoding="utf-8")
        csv = _csv(tmp_path, ten="rong")
        assert L.main(["--tong-hop", str(csv)]) == 1
        art = json.loads((tmp_path / "nhan" / "rong_tonghop.json").read_text(encoding="utf-8"))
        assert art["ket_qua"] is False and "hợp lệ" in art["ly_do"]

    def test_duong_dan_gon_khong_nem(self, tmp_path, monkeypatch):
        monkeypatch.setattr(L, "REPO_ROOT", tmp_path)
        assert L.duong_dan_gon(tmp_path / "a") == "a"                    # trong repo → gọn
        assert L.duong_dan_gon(Path("/tmp/khac/a")) == "/tmp/khac/a"      # ngoài repo → nguyên gốc


class TestChanHoiQuyVong3:
    """Các sửa vòng 3 là hành vi JS/luồng ⇒ giữ bằng cách kiểm chính mã nguồn (không thay được e2e)."""

    def test_loi_POST_khong_bi_nuot(self):
        h = (REPO / "tools" / "label_ui.html").read_text(encoding="utf-8")
        assert ".catch(() => {})" not in h, "nuốt lỗi POST ⇒ người dán tin là đã ghi (P2-3)"
        assert "LỖI GHI NHÃN" in h
        assert "if (await ghiNhan(state.nhanChon.nhan)) nhayBuoc(1)" in h, \
            "lỗi ghi mà vẫn nhảy bước là mất nhãn âm thầm"

    def test_buoc_duoc_GHIM_luc_bam_phim(self):
        h = (REPO / "tools" / "label_ui.html").read_text(encoding="utf-8")
        assert "function ghimBuoc" in h and "ghiNhanThat(nhan, g)" in h, \
            "tính lại bước trong hàng đợi ⇒ phán quyết của bước k rơi vào bước k+1 (P2-4)"

    def test_khong_dong_dau_buoc_tren_mousemove(self):
        h = (REPO / "tools" / "label_ui.html").read_text(encoding="utf-8")
        dong = [ln for ln in h.splitlines() if "veO.x1, veO.y1" in ln and "toaDoVideo" in ln]
        assert dong and all("veO.buoc" not in ln for ln in dong), \
            "đóng dấu `buoc` khi di chuột làm ô của bước trước trông như ô mới (P2-5)"

    def test_ten_da_luu_thang_mac_dinh_server(self):
        h = (REPO / "tools" / "label_ui.html").read_text(encoding="utf-8")
        i_luu = h.index("localStorage.getItem('labelui_nguoi')")
        i_md = h.index("d.nguoi_gan !== '?'")
        assert i_luu < i_md, "ưu tiên mặc định server ⇒ người thứ 2 ghi đè nhãn người thứ 1 (P1 vòng 3)"

    def test_phien_duoc_GHIM_cung_buoc(self):
        """Hàng đợi có thể tới lượt SAU khi người dùng đổi phiên ⇒ nhãn không được ghi sang phiên mới."""
        h = (REPO / "tools" / "label_ui.html").read_text(encoding="utf-8")
        assert "phien: g.phien" in h and "phien: state.phien, nhan" not in h
        assert "i, phien: state.phien, buoc" in h

    def test_ten_duoc_luu_ngay_khi_go(self):
        """Không đợi nhãn đầu thành công: người thứ 2 gõ tên rồi reload vẫn phải thấy tên MÌNH."""
        h = (REPO / "tools" / "label_ui.html").read_text(encoding="utf-8")
        i = h.index("$('nguoi').oninput")
        assert "localStorage.setItem('labelui_nguoi'" in h[i:i + 300]

    def test_server_tu_dien_frame_vos(self):
        p = (REPO / "tools" / "label_ui.py").read_text(encoding="utf-8")
        assert "\"frame_vos\": int(khung[buoc][\"frame_vos\"])" in p, \
            "không được tin `frame_vos` của client (P3-10)"
        assert "thiếu `buoc` — client phải gửi" in p, "thiếu `buoc` mà bỏ qua kiểm là lỗ (P3-10)"


class TestVideoPhatDuoc:
    """Chrome KHÔNG giải mã `mp4v` ⇒ `<video>` đen, mà bản cũ vẫn cho dán nhãn vào bước 0.

    Gặp thật 25-11: người dùng chọn `fast_1101-154036` (mpeg4/mp4v, 93/130 phiên cũ chưa có `_web.mp4`)
    ⇒ ảnh đen, không có bước VOS, nhưng vẫn ghi được 1 nhãn "ĐÚNG #0".
    """

    def test_dung_ban_web_neu_co(self, tmp_path, monkeypatch):
        monkeypatch.setattr(L, "DATA_DIR", tmp_path)
        (tmp_path / "s_web.mp4").write_bytes(b"\x00" * 100)
        (tmp_path / "s.mp4").write_bytes(b"\x00" * 100)
        assert L.video_de_phat("s") == ("s_web.mp4", True, None)

    def test_thieu_ban_web_thi_Chuyen_ma(self, tmp_path, monkeypatch):
        """Không có H.264 ⇒ phải chuyển mã tại chỗ (dùng chính `transcode_for_web` của repo)."""
        monkeypatch.setattr(L, "DATA_DIR", tmp_path)
        (tmp_path / "s.mp4").write_bytes(b"\x00" * 100)
        goi = {}

        def gia(src, dst=None, **k):
            goi["src"] = str(src)
            Path(dst).write_bytes(b"\x00" * 200)
            return str(dst)

        import src.worker as W
        monkeypatch.setattr(W, "transcode_for_web", gia)
        ten, ok, ghi_chu = L.video_de_phat("s")
        assert (ten, ok) == ("s_web.mp4", True) and ghi_chu and "chuyển mã" in ghi_chu
        assert goi["src"].endswith("s.mp4")

    def test_chuyen_ma_that_bai_thi_bao_RO(self, tmp_path, monkeypatch):
        """Thiếu ffmpeg ⇒ trả file gốc + `ok=False` + lý do; UI dùng cờ này để CHẶN ghi nhãn."""
        monkeypatch.setattr(L, "DATA_DIR", tmp_path)
        (tmp_path / "s.mp4").write_bytes(b"\x00" * 100)
        import src.worker as W
        monkeypatch.setattr(W, "transcode_for_web", lambda *a, **k: None)
        ten, ok, ghi_chu = L.video_de_phat("s")
        assert ten == "s.mp4" and ok is False
        assert "mp4v" in ghi_chu and "KHÔNG phát" in ghi_chu

    def test_khong_co_file_mp4(self, tmp_path, monkeypatch):
        monkeypatch.setattr(L, "DATA_DIR", tmp_path)
        assert L.video_de_phat("s") == (None, None, "không có file mp4 cho phiên s")

    def test_api_frames_tra_co_video_phat_duoc(self, tmp_path, monkeypatch):
        (tmp_path / "data").mkdir()
        (tmp_path / "data" / "v_metrics.csv").write_text(
            "frame_idx,latency_ms,center_x,center_y,bbox_w,bbox_h,mask_area\n0,100,10,10,4,4,9\n",
            encoding="utf-8")
        (tmp_path / "data" / "v.mp4").write_bytes(b"\x00" * 100)
        monkeypatch.setattr(L, "DATA_DIR", tmp_path / "data")
        monkeypatch.setattr(L, "THU_MUC_NHAN", tmp_path / "data" / "nhan")
        import src.worker as W
        monkeypatch.setattr(W, "transcode_for_web", lambda *a, **k: None)
        srv = L.tao_server(0, "B", None)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            d = json.load(urllib.request.urlopen(
                f"http://127.0.0.1:{srv.server_address[1]}/api/frames?phien=v"))
            assert d["video"] == "v.mp4" and d["video_phat_duoc"] is False
            assert "mp4v" in d["canh_bao_video"]
        finally:
            srv.shutdown()
            srv.server_close()


class TestAnhTungBuoc:
    """Chế độ ẢNH (dán nhanh): mỗi bước = 1 JPEG lấy từ video, cache trên đĩa.

    Người dùng yêu cầu 25-11: dừng video rồi chấm từng bước quá chậm ⇒ phải cắt sẵn frame.
    """

    @staticmethod
    def _video(tmp_path, monkeypatch, n_frame=30, fps=10.0):
        import cv2
        import numpy as np
        d = tmp_path / "data"
        d.mkdir()
        p = d / "phien1.mp4"
        w = cv2.VideoWriter(str(p), cv2.VideoWriter_fourcc(*"mp4v"), fps, (64, 48))
        for k in range(n_frame):
            khung = np.full((48, 64, 3), k * 8 % 255, np.uint8)
            w.write(khung)
        w.release()
        assert p.is_file() and p.stat().st_size > 0
        rows = "\n".join(f"{k},{100},10,10,4,4,9" for k in range(n_frame // 2))
        (d / "phien1_metrics.csv").write_text(
            "frame_idx,latency_ms,center_x,center_y,bbox_w,bbox_h,mask_area\n" + rows + "\n",
            encoding="utf-8")
        monkeypatch.setattr(L, "DATA_DIR", d)
        monkeypatch.setattr(L, "THU_MUC_NHAN", d / "nhan")
        monkeypatch.setattr(L, "_CAP", {})
        import src.worker as W
        monkeypatch.setattr(W, "transcode_for_web", lambda *a, **k: None)
        return d, p

    def test_chi_so_khung_va_he_so_bu(self, tmp_path, monkeypatch):
        """Phải khẳng định SỐ CỤ THỂ: bản đầu chỉ assert `0 <= idx < 30` nên xoá hẳn phép bù vẫn xanh."""
        self._video(tmp_path, monkeypatch)          # video 3,0 s / CSV 15 bước × 100 ms = 1,5 s
        d = L.doc_phien_cached(L.DATA_DIR / "phien1_metrics.csv")
        he_so, bi_kep = L.he_so_bu(3.0, d["tong_latency_s"])
        assert (round(he_so, 3), bi_kep) == (2.0, False), "3,0/1,5 = 2,0 vừa đúng biên, chưa bị kẹp"
        idx, loi = L.chi_so_khung("phien1", 0)
        assert loi is None and idx == 0
        buoc_cuoi = len(d["frames"]) - 1
        idx_cuoi, loi_cuoi = L.chi_so_khung("phien1", buoc_cuoi)
        assert loi_cuoi is None
        # 1,4 s × 2,0 × 10 fps = 28 — CON SỐ THẬT (không phải "0..30")
        assert idx_cuoi == 28, f"phải bù thời gian: 1,4s×2,0×10fps = 28, được {idx_cuoi}"
        # ngoài dải bước ⇒ None + LÝ DO (không trả ảnh bước 0)
        idx_xau, loi_xau = L.chi_so_khung("phien1", 999)
        assert idx_xau is None and "ngoài dải" in loi_xau

    def test_he_so_bu_bi_kep_duoc_bao(self):
        """Kẹp hệ số là lỗi mapping ⇒ phải có cờ, không im lặng (review 25-11, F10)."""
        assert L.he_so_bu(100.0, 1.5) == (2.0, True)      # 66× ⇒ kẹp trần
        assert L.he_so_bu(2.0, 100.0) == (0.5, True)      # 0,02× ⇒ kẹp sàn
        assert L.he_so_bu(1.0, 100.0) == (1.0, False)     # video ≤ 1 s ⇒ chưa đủ tin để bù
        assert L.he_so_bu(0.0, 10.0) == (1.0, False)      # không có video ⇒ không áp
        assert L.he_so_bu(10.0, 0.0) == (1.0, False)      # không có latency ⇒ không áp

    def test_anh_buoc_tra_jpeg_va_cache(self, tmp_path, monkeypatch):
        self._video(tmp_path, monkeypatch)
        du_lieu, loi = L.anh_buoc("phien1", 1)
        assert loi is None and du_lieu[:2] == b"\xff\xd8"      # magic bytes JPEG
        import cv2
        import numpy as np
        anh = cv2.imdecode(np.frombuffer(du_lieu, np.uint8), cv2.IMREAD_COLOR)
        assert anh.shape[:2] == (48, 64)
        tep = L.THU_MUC_NHAN / L.ANH_DIR_NAME / "phien1" / "000001.jpg"
        assert tep.is_file() and tep.read_bytes() == du_lieu        # lần 2 phục vụ từ đĩa
        lan2, loi2 = L.anh_buoc("phien1", 1)
        assert loi2 is None and lan2 == du_lieu

    def test_anh_buoc_khac_nhau_theo_buoc(self, tmp_path, monkeypatch):
        self._video(tmp_path, monkeypatch)
        a, _ = L.anh_buoc("phien1", 0)
        b, _ = L.anh_buoc("phien1", 5)
        assert a != b, "hai bước khác nhau phải ra hai khung hình khác nhau"

    @pytest.mark.parametrize("ten", ["../etc", "a/b", "", "phien1\x00"])
    def test_ten_phien_khong_hop_le(self, ten):
        assert L.anh_buoc(ten, 0)[0] is None

    def test_buoc_khong_phai_so(self, tmp_path, monkeypatch):
        self._video(tmp_path, monkeypatch)
        assert L.anh_buoc("phien1", "abc")[0] is None

    def test_khong_transcode_khi_lay_anh(self, tmp_path, monkeypatch):
        """Ảnh phải lấy từ FILE GỐC: chuyển mã cả clip (0,5–30 s) sẽ treo ảnh đầu vô ích.

        `cv2` đọc được `mp4v` (Chrome thì không) ⇒ không có lý do gọi `video_de_phat`.
        """
        self._video(tmp_path, monkeypatch)
        da_goi = []
        goc = L.video_de_phat
        monkeypatch.setattr(L, "video_de_phat", lambda ten: (da_goi.append(ten), goc(ten))[1])
        du_lieu, loi = L.anh_buoc("phien1", 0)
        assert loi is None and du_lieu[:2] == b"\xff\xd8"
        assert da_goi == [], "không được gọi video_de_phat (có thể transcode) khi chỉ cần frame"

    def test_khong_mo_duoc_video(self, tmp_path, monkeypatch):
        self._video(tmp_path, monkeypatch)
        L._CAP.clear()
        # không có file gốc `<ten>.mp4` ⇒ mới đi qua `video_de_phat`, và nó hỏng ⇒ None + lý do
        (L.DATA_DIR / "phien1.mp4").unlink()
        monkeypatch.setattr(L, "video_de_phat", lambda ten: (None, None, "không có"))
        assert L.anh_buoc("phien1", 0)[0] is None

    def test_cache_anh_khong_duoc_commit(self):
        """13 JPEG của cache từng lỡ vào repo (25-11): cache sinh lại được, `.gitignore` phải chặn."""
        gi = (REPO / ".gitignore").read_text(encoding="utf-8")
        assert "data/nhan/.anh/" in gi, "cache ảnh phải bị gitignore"
        assert L.ANH_DIR_NAME == ".anh", "tên thư mục cache trong code phải khớp `.gitignore`"

    def test_cache_cu_cua_buoc_ngoai_dai_khong_duoc_phuc_vu(self, tmp_path, monkeypatch):
        """CSV sinh lại còn ít bước mà cache cũ có `000999.jpg` ⇒ phải 404, không trả 200."""
        self._video(tmp_path, monkeypatch)
        d = L.THU_MUC_NHAN / L.ANH_DIR_NAME / "phien1"
        d.mkdir(parents=True, exist_ok=True)
        (d / "000999.jpg").write_bytes(b"\xff\xd8\xff\xd9")
        du_lieu, loi = L.anh_buoc("phien1", 999)
        assert du_lieu is None and "ngoài dải" in loi

    def test_cache_cut_duoc_cat_lai(self, tmp_path, monkeypatch):
        """Ghi cache không atomic từng để lại file cụt ⇒ mọi request sau trả ảnh HỎNG vĩnh viễn."""
        self._video(tmp_path, monkeypatch)
        d = L.THU_MUC_NHAN / L.ANH_DIR_NAME / "phien1"
        d.mkdir(parents=True, exist_ok=True)
        (d / "000001.jpg").write_bytes(b"\xff\xd8abc")
        du_lieu, loi = L.anh_buoc("phien1", 1)
        assert loi is None and du_lieu[:2] == b"\xff\xd8" and du_lieu[-2:] == b"\xff\xd9"
        assert (d / "000001.jpg").stat().st_size > 100, "phải ghi lại cache đầy đủ"

    def test_doi_nguon_thi_cat_lai_anh(self, tmp_path, monkeypatch):
        """CSV/video sinh lại ⇒ ảnh cache cũ KHÔNG còn đúng (fingerprint trong manifest)."""
        import os
        self._video(tmp_path, monkeypatch)
        d = L.THU_MUC_NHAN / L.ANH_DIR_NAME / "phien1"
        a, _ = L.anh_buoc("phien1", 2)
        csv_path = L.DATA_DIR / "phien1_metrics.csv"
        os.utime(csv_path, (1, 1))                  # mtime đổi ⇒ nguồn khác
        (d / "000002.jpg").write_bytes(b"\xff\xd8\xff\xd9")   # cache bẩn
        b, loi = L.anh_buoc("phien1", 2)
        assert loi is None and b != b"\xff\xd8\xff\xd9", "phải bỏ cache cũ, cắt lại từ video"

    def test_api_frames_khong_lam_ban_cache(self, tmp_path, monkeypatch):
        """`doc_phien_cached` trả object DÙNG CHUNG: trang trí lên nó ⇒ 2 người dùng chung server
        nhận nhãn của nhau + `rong/cao` có thể mất (review vòng 2, P1-1)."""
        self._video(tmp_path, monkeypatch)
        srv = L.tao_server(0, "B", None)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            goc = f"http://127.0.0.1:{srv.server_address[1]}"
            for nguoi in ("A", "B"):
                d = json.load(urllib.request.urlopen(
                    f"{goc}/api/frames?phien=phien1&nguoi={nguoi}"))
                assert d["rong"] == 64 and d["cao"] == 48
                assert "idx" in d["frames"][0] and "t_video_thuc" in d["frames"][0]
            cache = L.doc_phien_cached(L.DATA_DIR / "phien1_metrics.csv")
            assert "da_gan" not in cache and "rong" not in cache, "cache bị trang trí ⇒ rò giữa 2 request"
            assert all("idx" not in f for f in cache["frames"]), "frame trong cache bị thêm key"
        finally:
            srv.shutdown()
            srv.server_close()

    def test_api_frames_idx_khop_chi_so_khung_va_t_video_thuc(self, tmp_path, monkeypatch):
        """Hai đường tính `idx` (server trang trí `/api/frames` vs `chi_so_khung`) phải TRÙNG; nếu lệch
        thì panel `t≈` một đằng mà ảnh một nẻo."""
        self._video(tmp_path, monkeypatch)
        srv = L.tao_server(0, "B", None)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            d = json.load(urllib.request.urlopen(
                f"http://127.0.0.1:{srv.server_address[1]}/api/frames?phien=phien1"))
            assert d["frames"], "phải có bước"
            for f in d["frames"]:
                idx, loi = L.chi_so_khung("phien1", f["buoc"])
                assert loi is None and f["idx"] == idx, f"bước {f['buoc']}: {f['idx']} vs {idx}"
                assert f["t_video_thuc"] == round(f["idx"] / d["fps"], 3)
        finally:
            srv.shutdown()
            srv.server_close()

    def test_hai_nguoi_cung_luc_moi_nguoi_chi_thay_nhan_cua_minh(self, tmp_path, monkeypatch):
        """2 request `/api/frames` CHỒNG NHAU (2 người dùng chung 1 server) không được trộn nhãn."""
        self._video(tmp_path, monkeypatch)
        nhan = L.THU_MUC_NHAN / "phien1.jsonl"
        nhan.parent.mkdir(parents=True, exist_ok=True)
        dong = []
        for nguoi, b in (("A", 1), ("B", 2), ("B", 3)):
            dong.append(json.dumps({"phien": "phien1", "buoc": b, "frame_vos": b, "nhan": "dung",
                                    "nguoi_gan": nguoi, "t_video": 0.1 * b, "t_uoc_luong": 0.1 * b,
                                    "git_rev": "t", "do_luc": "t"}))
        nhan.write_text("\n".join(dong) + "\n", encoding="utf-8")
        srv = L.tao_server(0, "B", None)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            goc = f"http://127.0.0.1:{srv.server_address[1]}"
            ket: dict[str, list] = {}
            rao = threading.Barrier(2)

            def mot(nguoi):
                rao.wait()                      # cùng lúc
                d = json.load(urllib.request.urlopen(f"{goc}/api/frames?phien=phien1&nguoi={nguoi}"))
                ket[nguoi] = [r["nguoi_gan"] for r in d["da_gan"]]

            ts = [threading.Thread(target=mot, args=(n,)) for n in ("A", "B")]
            [t.start() for t in ts]
            [t.join() for t in ts]
            assert ket["A"] == ["A"], f"A nhận nhãn của người khác: {ket['A']}"
            assert ket["B"] == ["B", "B"], f"B nhận nhãn lẫn: {ket['B']}"
        finally:
            srv.shutdown()
            srv.server_close()

    def test_che_do_duoc_ghi_vao_nhan(self, tmp_path, monkeypatch):
        """`t_video` có hai nguồn khác nhau ⇒ file bằng chứng phải nói nhãn dán ở chế độ nào."""
        rec = L.ghi_nhan("phien1", {"buoc": 1, "frame_vos": 1, "nhan": "dung",
                                    "t_video": 0.1, "t_uoc_luong": 0.1, "che_do": "anh"},
                         "A", tmp_path)
        assert rec["che_do"] == "anh"
        rec2 = L.ghi_nhan("phien1", {"buoc": 1, "frame_vos": 1, "nhan": "dung",
                                     "t_video": 0.1, "t_uoc_luong": 0.1}, "A", tmp_path)
        assert rec2["che_do"] is None, "không khai thì để None, đừng bịa 'video'"
        with pytest.raises(ValueError):
            L.ghi_nhan("phien1", {"buoc": 1, "frame_vos": 1, "nhan": "dung", "che_do": "auto"},
                       "A", tmp_path)

    def test_route_anh_thieu_buoc_400(self, tmp_path, monkeypatch):
        self._video(tmp_path, monkeypatch)
        srv = L.tao_server(0, "B", None)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            with pytest.raises(urllib.error.HTTPError) as e:
                urllib.request.urlopen(
                    f"http://127.0.0.1:{srv.server_address[1]}/anh?phien=phien1")
            assert e.value.code == 400, "thiếu `buoc` KHÔNG được mặc định về bước 0"
        finally:
            srv.shutdown()
            srv.server_close()

    def test_route_anh_tra_jpeg_va_404(self, tmp_path, monkeypatch):
        self._video(tmp_path, monkeypatch)
        srv = L.tao_server(0, "B", None)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            goc = f"http://127.0.0.1:{srv.server_address[1]}"
            with urllib.request.urlopen(goc + "/anh?phien=phien1&buoc=2") as r:
                assert r.headers["Content-Type"] == "image/jpeg"
                assert r.read()[:2] == b"\xff\xd8"
            with pytest.raises(urllib.error.HTTPError) as e:
                urllib.request.urlopen(goc + "/anh?phien=khong_co&buoc=0")
            assert e.value.code == 404
        finally:
            srv.shutdown()
            srv.server_close()

    def test_api_frames_tra_rong_cao_cua_video(self, tmp_path, monkeypatch):
        self._video(tmp_path, monkeypatch)
        srv = L.tao_server(0, "B", None)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            d = json.load(urllib.request.urlopen(
                f"http://127.0.0.1:{srv.server_address[1]}/api/frames?phien=phien1"))
            assert (d["rong"], d["cao"]) == (64, 48)      # UI quy đổi ảnh đã thu nhỏ → pixel video
            assert d["che_do_mac_dinh"] == "anh"
        finally:
            srv.shutdown()
            srv.server_close()

    def test_cap_khong_bi_dung_song_song(self, tmp_path, monkeypatch):
        """FFmpeg không thread-safe ⇒ chỉ được mở **MỘT** `VideoCapture` cho một phiên.

        Bản đầu chỉ assert "không ném": bỏ hẳn `_CAP_LOCK` mà FFmpeg không assert lần đó thì test vẫn
        xanh. Nay đếm constructor (review 25-11, F11).
        """
        import cv2
        self._video(tmp_path, monkeypatch, n_frame=40)
        so_lan_mo = []
        that = cv2.VideoCapture

        class Dem:
            def __init__(self, *a, **k):
                so_lan_mo.append(a[0] if a else "")
                self._c = that(*a, **k)
            def __getattr__(self, n):
                return getattr(self._c, n)

        monkeypatch.setattr(cv2, "VideoCapture", Dem)
        ket, loi = [], []
        def mot(b):
            d, e = L.anh_buoc("phien1", b)
            (ket.append(d) if d else loi.append(e))
        ts = [threading.Thread(target=mot, args=(b,)) for b in range(3, 15)]
        [t.start() for t in ts]
        [t.join() for t in ts]
        assert not loi and len(ket) == 12
        assert len(so_lan_mo) == 1, f"phải mở đúng 1 capture, đã mở {len(so_lan_mo)}"
        assert ket[0] != ket[-1], "12 bước khác nhau phải ra ảnh khác nhau"

    def test_cap_cu_duoc_release_khi_duoi(self, tmp_path, monkeypatch):
        """`_CAP.clear()` trần để rò file descriptor — phải `release()` cái bị đuổi."""
        import cv2
        self._video(tmp_path, monkeypatch, n_frame=10)
        so_release = []
        that = cv2.VideoCapture

        class Dem:
            def __init__(self, *a, **k):
                self._c = that(*a, **k)
            def __getattr__(self, n):
                return getattr(self._c, n)
            def release(self):
                so_release.append(1)
                return self._c.release()

        monkeypatch.setattr(cv2, "VideoCapture", Dem)
        monkeypatch.setattr(L, "_CAP_MAX", 2)   # MAX=2 + 3 phiên ⇒ phải đuổi ĐÚNG cái CŨ NHẤT
        for ten in ("phien1", "phienB", "phienC"):
            (L.DATA_DIR / f"{ten}.mp4").write_bytes((L.DATA_DIR / "phien1.mp4").read_bytes())
            (L.DATA_DIR / f"{ten}_metrics.csv").write_text(
                (L.DATA_DIR / "phien1_metrics.csv").read_text(encoding="utf-8"), encoding="utf-8")
        L._CAP.clear()
        for ten in ("phien1", "phienB", "phienC"):
            L.anh_buoc(ten, 0)
        assert set(L._CAP) == {"phienB", "phienC"}, f"phải đuổi cái CŨ NHẤT: {sorted(L._CAP)}"
        assert len(so_release) >= 1, f"capture bị đuổi phải release(), mới release {len(so_release)}"


class TestClientHuyKetNoi:
    """Chrome huỷ request Range khi tua video ⇒ `write()` ném ConnectionResetError và `http.server` in
    traceback 20 dòng vào terminal đang dán nhãn (người dùng báo 25-11). Video vẫn phát bình thường —
    đây là rác log phải nuốt, KHÔNG được ảnh hưởng phiên."""

    @pytest.mark.parametrize("loi", [ConnectionResetError(104, "Connection reset by peer"),
                                     BrokenPipeError(32, "Broken pipe"),
                                     ConnectionAbortedError(103, "Software caused connection abort")])
    def test_ghi_an_toan_khong_nem(self, loi):
        class Wfile:
            def write(self, b):
                raise loi
            def flush(self):
                pass

        assert L.ghi_an_toan(Wfile(), b"x") is False

    def test_ghi_an_toan_binh_thuong(self):
        class Wfile:
            def __init__(self):
                self.da = b""

            def write(self, b):
                self.da += b

        w = Wfile()
        assert L.ghi_an_toan(w, b"abc") is True and w.da == b"abc"

    def test_video_khong_no_traceback_khi_client_huy(self, tmp_path, monkeypatch):
        """Gọi thật `_video` với `wfile` ném giữa đường ⇒ không ném ra ngoài."""
        (tmp_path / "data").mkdir()
        (tmp_path / "data" / "v_web.mp4").write_bytes(b"\x00" * 4096)
        monkeypatch.setattr(L, "DATA_DIR", tmp_path / "data")
        srv = L.tao_server(0, "B", None)
        httph = srv.RequestHandlerClass
        obj = object.__new__(httph)                    # không mở socket: chỉ kiểm đường ghi
        obj.headers = {"Range": "bytes=0-99"}
        obj.send_response = lambda *a, **k: None
        obj.send_header = lambda *a, **k: None
        obj.end_headers = lambda: None
        obj._json = lambda *a, **k: None

        class Wfile:
            def write(self, b):
                raise ConnectionResetError(104, "Connection reset by peer")

            def flush(self):
                pass

        obj.wfile = Wfile()
        try:
            obj._video({"v": ["v_web.mp4"]})
        finally:
            srv.server_close()


class TestHangSoVaTaiLieu:
    def test_tap_nhan_dung_nhu_thiet_ke(self):
        """Phải so ĐÚNG TẬP: thiếu nhãn thì `tong_hop` đếm thiếu mà test mô tả vẫn xanh."""
        assert set(L.NHAN) == {"dung", "sai", "mat_dau", "khong_co_vat", "bo_qua"}

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
        assert "Space" in s, "hướng dẫn nhắc Space thì CODE phải có nhánh Space"
        assert "`E` rồi kéo chuột" in s, "hướng dẫn phải nói phím vẽ ô là E"
        assert '"Nguyen"' in s, "phải cảnh báo: `e` không ăn khi gõ tên"
        assert "CHUA XAC MINH" in s and "KHÔNG có cột" in s, \
            "phải nói rõ `chua_xac_minh` KHÔNG có cột trong CSV (bản đầu mô tả sai là 'không vẽ')"
        assert "so_buoc_dong_y" in s, "khoá JSON trong doc phải khớp `tong_hop` thật"

    def test_html_CHAN_ghi_nhan_khi_video_khong_phat_duoc(self):
        """Nhãn mù tệ hơn không có nhãn — đúng ca 25-11 (ảnh đen mà vẫn ghi được "ĐÚNG #0")."""
        h = (REPO / "tools" / "label_ui.html").read_text(encoding="utf-8")
        assert "function datTrangThaiVideo" in h
        # 25-11 (tối): thêm chế độ ẢNH ⇒ điều kiện phải theo CHẾ ĐỘ đang xem (ảnh tải được là đủ),
        # nhưng vẫn phải CHẶN khi nguồn đang xem không hiện được.
        assert "state.cheDo === 'anh' ? !state.anhOk : !state.videoOk" in h, \
            "ghiNhan phải từ chối khi NGUỒN ĐANG XEM (ảnh hoặc video) chưa hiện được"
        assert "state.anhOk" in h and "state.videoOk" in h
        assert "addEventListener('error'" in h, "phải bắt lỗi giải mã để báo, không im lặng"
        assert "KHÔNG PHÁT ĐƯỢC VIDEO" in h

    def test_html_anh_khong_bat_khoa_khi_anh_khong_hien(self):
        """`src` không đổi KHÔNG có nghĩa ảnh đang hiện (ảnh lỗi vẫn giữ src cũ) ⇒ cấm bật khoá ghi."""
        h = (REPO / "tools" / "label_ui.html").read_text(encoding="utf-8")
        assert "im.complete && im.naturalWidth > 0" in h, \
            "nhánh 'src không đổi' phải kiểm ảnh có thật trước khi cho ghi nhãn"
        assert "if (tenCu !== ten) state.i = 0;" in h, \
            "đổi PHIÊN phải về bước 0 (guard cũ so sau khi đã gán nên không bao giờ chạy)"
        assert "(state.cheDo === 'anh') ? 0 :" in h, \
            "chế độ ảnh không được bắn cảnh báo LỆCH (luôn đứng đúng bước)"

    def test_html_khoa_ghi_nhan_theo_nguon_dang_xem(self):
        """Chế độ ẢNH không được khoá oan vì <video> của phiên mp4v không phát được."""
        h = (REPO / "tools" / "label_ui.html").read_text(encoding="utf-8")
        assert "function capNhatKhoa" in h
        assert "(state.cheDo === 'anh') ? state.anhOk : state.videoOk" in h, \
            "khoá nút phải theo nguồn đang xem"
        body = h.split("function capNhatKhoa")[1].split("function datTrangThaiVideo")[0]
        assert "disabled = !cho" in body or "disabled = !cho" in h
        # banner đỏ chỉ dành cho chế độ video
        assert "if (ok || state.cheDo === 'anh')" in h, \
            "chế độ ảnh không được phủ banner 'KHÔNG PHÁT ĐƯỢC VIDEO' lên ảnh"

    def test_html_phim_ve_o_la_E_va_khong_pha_go_ten(self):
        """`E` = phím vẽ ô (gần cụm 1/2/3/4); `e` KHÔNG được ăn khi gõ tên ("Nguyen" có chữ e)."""
        h = (REPO / "tools" / "label_ui.html").read_text(encoding="utf-8")
        assert "const laPhimVeO = ['e','E','b','B']" in h, "E (và b cũ) phải là phím vẽ ô"
        assert "else if (laPhimVeO) {" in h, "nhánh vẽ ô phải dùng laPhimVeO"
        # `e`/`b` KHÔNG được nằm trong danh sách "ăn cả khi đang ở ô tên"
        dong = [d for d in h.splitlines() if "const laPhimNhan =" in d]
        assert dong and "b" not in dong[0] and "'e'" not in dong[0], \
            f"laPhimNhan không được chứa phím vẽ ô: {dong}"
        assert "if (trongOText && !laPhimNhan) return;" in h, "phải chặn phím vẽ khi đang gõ tên"
        assert "<kbd>E</kbd> rồi kéo chuột" in h, "hướng dẫn trong UI phải nói E"

    def test_html_khong_hua_phim_khong_ton_tai(self):
        """Doc/comment hứa `Space` = phát/dừng ⇒ file HTML phải thật sự có nhánh xử lý Space."""
        h = (REPO / "tools" / "label_ui.html").read_text(encoding="utf-8")
        assert "k === ' '" in h, "mất nhánh Space ⇒ hướng dẫn sai (đúng lỗi review P2-1)"
        assert "pointer-events:none" in h, "canvas nuốt chuột của <video controls> nếu thiếu"
