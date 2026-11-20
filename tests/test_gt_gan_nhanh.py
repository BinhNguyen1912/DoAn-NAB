"""Test công cụ gán GT nhanh (`scripts/gt_gan_nhanh.py` + `gt_painter.html`).

Vì sao test ở mức này: GT là **thước đo duy nhất** của "bám đúng" ⇒ lỗi trong đường gán GT làm mọi con
số mIoU sai. Ba bẫy đã gặp trong repo, mỗi bẫy một test:

1. `IoU(rỗng, rỗng) = 1,0` ⇒ GT rỗng bị nhận là "bám đúng tuyệt đối" (`_kiem_png` phải TỪ CHỐI);
2. GT khác kích thước frame ⇒ `score_miou` chỉ so `sum` nên **không** phát hiện (`_kiem_png` phải TỪ CHỐI);
3. `nguon_gt` khai man ("người tô tay") khi thật ra khởi tạo từ ngưỡng màu ⇒ `index.json` phải khai đúng.
"""

from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import numpy as np
import pytest

from scripts import gt_gan_nhanh as gt


# ── gợi ý màu ────────────────────────────────────────────────────────────────────────────


def test_goi_y_rong_khi_anh_khong_co_mau():
    """Ảnh xám ⇒ KHÔNG gợi ý được (trả mask rỗng), không được ném lỗi cv2 khó hiểu."""
    xam = np.full((40, 40), 120, np.uint8)
    assert int((gt.goi_y_hsv(xam) > 127).sum()) == 0


def test_goi_y_bat_vat_mau_va_bo_nen_xam():
    """Nền xám + một khối màu đỏ ⇒ gợi ý phủ khối màu, KHÔNG phủ nền."""
    import cv2

    img = np.full((120, 160, 3), 200, np.uint8)          # nền sáng, gần như không bão hoà
    cv2.rectangle(img, (40, 30), (90, 110), (40, 20, 200), -1)   # khối màu (BGR)
    mask = gt.goi_y_hsv(img)
    assert mask.shape == (120, 160)
    assert mask[70, 65] > 127, "phải phủ giữa khối màu"
    assert mask[5, 5] < 128, "không được phủ nền"


def test_goi_y_lap_nhan_trang_ben_trong_bang_bao_loi():
    """Nhãn trắng giữa vật ⇒ phần giữa vẫn phải nằm trong gợi ý (nhờ bao lồi)."""
    import cv2

    img = np.full((120, 160, 3), 200, np.uint8)
    cv2.rectangle(img, (40, 30), (90, 110), (40, 20, 200), -1)
    cv2.rectangle(img, (55, 60), (75, 80), (250, 250, 250), -1)  # nhãn trắng = bão hoà thấp
    mask = gt.goi_y_hsv(img)
    assert mask[70, 65] > 127, "bao lồi phải lấp vùng nhãn trắng ở giữa"


def test_goi_y_anh_rong_thi_bao_loi_ro_rang():
    with pytest.raises(ValueError):
        gt.goi_y_hsv(np.zeros((0, 0, 3), np.uint8))


# ── tên file ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("ten,mong_doi", [
    ("frame_000057.png", 57), ("goiy_000057.png", 57), ("gt_000057.png", 57),
    ("frame_000000.png", 0), ("anh_57.png", None), ("frame_abc.png", None),
    ("frame_57.jpg", 57), ("../../etc/passwd", None), ("frame_000057.png.bak", None),
])
def test_doc_frame_tu_ten(ten, mong_doi):
    assert gt.doc_frame_tu_ten(ten) == mong_doi


# ── index.json ──────────────────────────────────────────────────────────────────────────


def test_index_khai_dung_nguon_gt_khi_co_goi_y(tmp_path):
    """Có gợi ý màu ⇒ `nguon_gt` phải NÓI RA, và sai số bộ gợi ý phải khai là CHƯA ĐO."""
    path = gt._viet_index(tmp_path, clip="data/binh1.mp4", ten="t1", frames=[5, 1, 5],
                          nguoi_gan="A", co_goi_y=True)
    index = json.loads(path.read_text(encoding="utf-8"))
    assert index["dang_gt"] == "silhouette"
    assert "ngưỡng màu" in index["nguon_gt"]
    assert "CHƯA ĐO" in index["sai_so_bo_goi_y"]
    assert index["gt_do_model_goi_y"] is False          # GT từ ngưỡng màu, KHÔNG phải từ model
    assert [f["frame_idx"] for f in index["frames"]] == [1, 5]     # sắp xếp + bỏ trùng


def test_index_khai_to_tay_khi_khong_goi_y(tmp_path):
    path = gt._viet_index(tmp_path, clip="c.mp4", ten="t2", frames=[0],
                          nguoi_gan="A", co_goi_y=False)
    index = json.loads(path.read_text(encoding="utf-8"))
    assert index["nguon_gt"] == "người tô tay trên frame gốc"
    assert index["sai_so_bo_goi_y"] is None


# ── kiểm ảnh GT do trình duyệt gửi lên ──────────────────────────────────────────────────


def _png(mask: np.ndarray) -> bytes:
    import cv2

    ok, buf = cv2.imencode(".png", mask.astype(np.uint8))
    assert ok
    return buf.tobytes()


def test_kiem_png_tu_choi_mask_rong():
    """Mask rỗng ⇒ `IoU(rỗng, rỗng) = 1,0` ⇒ phải TỪ CHỐI, không lưu."""
    loi = gt._kiem_png(_png(np.zeros((40, 50), np.uint8)), rong=50, cao=40)
    assert "rỗng" in loi


def test_kiem_png_tu_choi_sai_kich_thuoc():
    loi = gt._kiem_png(_png(np.full((40, 50), 255, np.uint8)), rong=60, cao=40)
    assert "kích thước" in loi


def test_kiem_png_tu_choi_du_lieu_khong_phai_anh():
    assert gt._kiem_png(b"khong phai png", rong=10, cao=10) != ""


def test_kiem_png_nhan_anh_hop_le():
    assert gt._kiem_png(_png(np.full((40, 50), 255, np.uint8)), rong=50, cao=40) == ""


# ── server: lưu thẳng vào thư mục GT ────────────────────────────────────────────────────


@pytest.fixture()
def may_chu(tmp_path):
    (tmp_path / "frames").mkdir()
    (tmp_path / "goiy").mkdir()
    kich_thuoc = {57: (50, 40)}
    server = ThreadingHTTPServer(("127.0.0.1", 0), gt._make_handler(tmp_path, kich_thuoc))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}", tmp_path
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def _post(url: str, data: bytes):
    req = urllib.request.Request(url, data=data, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, r.read().decode()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode()


def test_server_luu_gt_dung_thu_muc(may_chu):
    base, tmp_path = may_chu
    status, text = _post(f"{base}/luu/gt_000057.png", _png(np.full((40, 50), 255, np.uint8)))
    assert status == 200, text
    assert (tmp_path / "gt_000057.png").is_file(), "GT phải nằm thẳng trong thư mục GT"


def test_server_tu_choi_frame_la_va_duong_dan_lac(may_chu):
    base, tmp_path = may_chu
    status, _ = _post(f"{base}/luu/../../etc/passwd", _png(np.full((40, 50), 255, np.uint8)))
    assert status in (400, 404)
    status, _ = _post(f"{base}/luu/gt_000058.png", _png(np.full((40, 50), 255, np.uint8)))
    assert status == 400, "frame không có trong danh sách ⇒ từ chối"
    assert not list(tmp_path.glob("gt_*.png"))


def test_server_tu_choi_mask_rong_va_sai_co(may_chu):
    base, tmp_path = may_chu
    # Mask RỖNG nhưng ĐÚNG cỡ: nếu sai cỡ thì cổng "kích thước" chặn trước và test không kiểm được
    # đúng bẫy `IoU(rỗng, rỗng) = 1,0`.
    status, text = _post(f"{base}/luu/gt_000057.png", _png(np.zeros((40, 50), np.uint8)))
    assert status == 422 and "rỗng" in text
    status, _ = _post(f"{base}/luu/gt_000057.png", _png(np.full((10, 10), 255, np.uint8)))
    assert status == 422
    assert not list(tmp_path.glob("gt_*.png"))


def test_server_phuc_vu_frame_goi_y_va_gt(may_chu):
    base, tmp_path = may_chu
    import cv2

    cv2.imwrite(str(tmp_path / "frames" / "frame_000057.png"), np.zeros((40, 50, 3), np.uint8))
    for duong in ("/frame/frame_000057.png", "/goiy/goiy_000057.png", "/gt/gt_000057.png"):
        try:
            with urllib.request.urlopen(base + duong, timeout=10) as r:
                assert r.status == 200 or duong.startswith(("/goiy", "/gt"))
        except urllib.error.HTTPError as exc:
            assert exc.code == 404, f"{duong} phải 404 (chưa có file) chứ không 500"
    with urllib.request.urlopen(base + "/danh-sach.json", timeout=10) as r:
        info = json.loads(r.read())
    assert info["frames"] == [57]


def test_trang_to_co_mat_va_khong_dung_file_ngoai(may_chu):
    base, _tmp = may_chu
    with urllib.request.urlopen(base + "/", timeout=10) as r:
        html = r.read().decode()
    assert "Lưu" in html and "canvas" in html
    # Trình tô không được tải tài nguyên ngoài (chạy offline trong phòng demo)
    assert "http://" not in html.replace("http://127.0.0.1", "") and "https://" not in html


class TestIndexKhongXoaDuLieuCu:
    """Gọi lại trên thư mục ĐÃ có `index.json` không được xoá dấu vết (review PR #49, P1).

    Ghi đè trắng làm frame đã gán rơi khỏi index ⇒ `n_cham` nhỏ đi nhưng `coverage` vẫn 1,0 (số liệu
    nhỏ dần một cách im lặng), và xoá cả `dung_duoc: false` — tức bộ GT đã bị vô hiệu hoá lại thành
    "dùng được".
    """

    def test_giu_frame_cu_va_khoa_la(self, tmp_path):
        cu = {"frames": [{"frame_idx": 10}, {"frame_idx": 20}], "dung_duoc": False,
              "ly_do_khong_dung": "GT vẽ bằng hộp, không phải silhouette", "frame_hw": [720, 1280]}
        (tmp_path / "index.json").write_text(json.dumps(cu), encoding="utf-8")
        path = gt._viet_index(tmp_path, clip="c.mp4", ten="t", frames=[30],
                              nguoi_gan="A", co_goi_y=True, frame_hw=[720, 1280])
        moi = json.loads(path.read_text(encoding="utf-8"))
        assert [f["frame_idx"] for f in moi["frames"]] == [10, 20, 30], "frame cũ không được rơi"
        assert moi["dung_duoc"] is False, "không được xoá cờ vô hiệu hoá của bộ GT cũ"
        assert "hộp" in moi["ly_do_khong_dung"]

    def test_index_hong_thi_van_ghi_duoc(self, tmp_path):
        (tmp_path / "index.json").write_text("{khong phai json", encoding="utf-8")
        path = gt._viet_index(tmp_path, clip="c.mp4", ten="t", frames=[5], nguoi_gan="A",
                              co_goi_y=False, frame_hw=[40, 50])
        moi = json.loads(path.read_text(encoding="utf-8"))
        assert [f["frame_idx"] for f in moi["frames"]] == [5]
        assert moi["frame_hw"] == [40, 50]      # cổng kích thước GT chỉ chạy khi CÓ khoá này


class TestKhaiFrameKhongCoVat:
    """Frame không có vật phải khai được (`?rong=1`), nhưng rỗng KHÔNG được nhận vô điều kiện.

    `binh1` có frame chai đã rời khung: ép tô một vật không tồn tại là tạo GT sai, còn bắt dừng giữa
    buổi thì không ra được con số nào (review PR #49, P1).
    """

    def test_kiem_png_rong_bi_tu_choi_khi_khong_khai(self):
        loi = gt._kiem_png(_png(np.zeros((40, 50), np.uint8)), rong=50, cao=40)
        assert "rỗng" in loi and "Không có vật" in loi

    def test_kiem_png_rong_duoc_nhan_khi_da_khai(self):
        assert gt._kiem_png(_png(np.zeros((40, 50), np.uint8)), rong=50, cao=40,
                            cho_rong=True) == ""

    def test_ghi_gt_rong_vao_index(self, tmp_path):
        (tmp_path / "index.json").write_text(json.dumps({"frames": [{"frame_idx": 90}]}),
                                             encoding="utf-8")
        gt._ghi_gt_rong(tmp_path, 90)
        gt._ghi_gt_rong(tmp_path, 90)          # gọi 2 lần không được nhân đôi
        index = json.loads((tmp_path / "index.json").read_text(encoding="utf-8"))
        assert index["gt_rong"] == [90]
        assert index["frames"] == [{"frame_idx": 90}], "không được ghi đè các khoá khác"

    def test_ghi_gt_rong_khong_no_khi_index_hong(self, tmp_path):
        (tmp_path / "index.json").write_text("hỏng", encoding="utf-8")
        gt._ghi_gt_rong(tmp_path, 5)           # không được ném lỗi
        assert (tmp_path / "index.json").read_text(encoding="utf-8") == "hỏng"


class TestServerKhaiRongVaChanOrigin:
    def test_post_rong_1_duoc_nhan_va_ghi_gt_rong(self, tmp_path):
        import threading

        from http.server import ThreadingHTTPServer

        (tmp_path / "frames").mkdir()
        (tmp_path / "index.json").write_text(json.dumps({"frames": [{"frame_idx": 57}]}),
                                             encoding="utf-8")
        server = ThreadingHTTPServer(("127.0.0.1", 0), gt._make_handler(tmp_path, {57: (50, 40)}))
        th = threading.Thread(target=server.serve_forever, daemon=True)
        th.start()
        try:
            url = f"http://127.0.0.1:{server.server_address[1]}/luu/gt_000057.png"
            status, text = _post(url + "?rong=1", _png(np.zeros((40, 50), np.uint8)))
            assert status == 200, text
            index = json.loads((tmp_path / "index.json").read_text(encoding="utf-8"))
            assert index["gt_rong"] == [57]
            # cùng payload nhưng KHÔNG khai ⇒ 422 (không được nhận rỗng vô điều kiện)
            status, _ = _post(url, _png(np.zeros((40, 50), np.uint8)))
            assert status == 422
        finally:
            server.shutdown()
            server.server_close()
            th.join(timeout=5)

    def test_post_tu_origin_khac_bi_chan(self, tmp_path):
        import threading

        from http.server import ThreadingHTTPServer

        (tmp_path / "frames").mkdir()
        server = ThreadingHTTPServer(("127.0.0.1", 0), gt._make_handler(tmp_path, {57: (50, 40)}))
        th = threading.Thread(target=server.serve_forever, daemon=True)
        th.start()
        try:
            url = f"http://127.0.0.1:{server.server_address[1]}/luu/gt_000057.png"
            req = urllib.request.Request(url, data=_png(np.full((40, 50), 255, np.uint8)),
                                         method="POST",
                                         headers={"Sec-Fetch-Site": "cross-site"})
            try:
                with urllib.request.urlopen(req, timeout=10) as r:
                    kq = r.status
            except urllib.error.HTTPError as exc:
                kq = exc.code
            assert kq == 403
            assert not list(tmp_path.glob("gt_*.png"))
        finally:
            server.shutdown()
            server.server_close()
            th.join(timeout=5)

    def test_content_length_hong_tra_400_khong_chet_handler(self, tmp_path):
        import socket
        import threading

        from http.server import ThreadingHTTPServer

        (tmp_path / "frames").mkdir()
        server = ThreadingHTTPServer(("127.0.0.1", 0), gt._make_handler(tmp_path, {57: (50, 40)}))
        th = threading.Thread(target=server.serve_forever, daemon=True)
        th.start()
        try:
            with socket.create_connection(("127.0.0.1", server.server_address[1]), timeout=10) as s:
                s.sendall(b"POST /luu/gt_000057.png HTTP/1.1\r\nHost: x\r\n"
                          b"Content-Length: abc\r\n\r\n")
                tra_loi = s.recv(200).decode("latin-1")
            assert "400" in tra_loi.splitlines()[0]
            assert not list(tmp_path.glob("gt_*.png"))
        finally:
            server.shutdown()
            server.server_close()
            th.join(timeout=5)


class TestTenBoGtHopLe:
    @pytest.mark.parametrize("ten,hop_le", [
        ("binh1_tay", True), ("a", True), ("a.b-c", True),
        ("../docs", False), ("..", False), ("/etc", False), (".an", False), ("a/b", False),
    ])
    def test_ten_bo_gt(self, ten, hop_le):
        assert bool(gt.TEN_HOP_LE.match(ten)) is hop_le


class TestKhongTronPhuongPhapGan:
    """Bộ GT dạng `hop_bao` KHÔNG được bị công cụ silhouette ghi vào (review PR #49 vòng 2, P1).

    `docs/gt/binh1_hopbao/index.json` khai `dang_gt: hop_bao` + `hop_bao_xywh` từng frame. Nếu ghi đè:
    cổng `hop_bao_xywh`↔mask của `score_miou.kiem_index` **tắt im lặng**, artifact đổi `gt_dang` ⇒ con số
    `mIoU 0,6464` bị in thành "IoU với GT silhouette" (dán nhãn sai một số đã công bố).
    """

    def test_tu_choi_khi_bo_gt_cu_la_hop_bao(self, tmp_path):
        cu = {"dang_gt": "hop_bao", "frames": [
            {"frame_idx": 3, "hop_bao_xywh": [10, 10, 20, 30]}]}
        (tmp_path / "index.json").write_text(json.dumps(cu), encoding="utf-8")
        with pytest.raises(SystemExit) as loi:
            gt._viet_index(tmp_path, clip="c.mp4", ten="hopbao", frames=[99],
                           nguoi_gan="A", co_goi_y=True, frame_hw=[40, 50])
        assert "hop_bao" in str(loi.value)
        # index cũ phải NGUYÊN VẸN
        assert json.loads((tmp_path / "index.json").read_text(encoding="utf-8")) == cu

    def test_giu_hop_bao_xywh_tung_frame_khi_silhouette(self, tmp_path):
        """Cùng dạng silhouette nhưng frame cũ có khoá riêng (`hop_bao_xywh`, `ghi_chu`) ⇒ phải giữ."""
        cu = {"dang_gt": "silhouette", "frames": [
            {"frame_idx": 3, "hop_bao_xywh": [10, 10, 20, 30], "ghi_chu": "vật bị che 50 %"}]}
        (tmp_path / "index.json").write_text(json.dumps(cu), encoding="utf-8")
        path = gt._viet_index(tmp_path, clip="c.mp4", ten="t", frames=[3, 9],
                              nguoi_gan="B", co_goi_y=True, frame_hw=[40, 50])
        moi = json.loads(path.read_text(encoding="utf-8"))
        f3 = [f for f in moi["frames"] if f["frame_idx"] == 3][0]
        assert f3["hop_bao_xywh"] == [10, 10, 20, 30], "mất hộp bao của frame cũ"
        assert f3["ghi_chu"] == "vật bị che 50 %"
        assert [f["frame_idx"] for f in moi["frames"]] == [3, 9]

    def test_khong_viet_lai_nguon_gt_cua_frame_da_gan(self, tmp_path):
        """Lần đầu tô tay, lần sau có gợi ý ⇒ KHÔNG được đổi `nguon_gt` (hai phương pháp trong một bộ)."""
        cu = {"dang_gt": "silhouette", "nguon_gt": "người tô tay trên frame gốc",
              "phuong_phap_gt": "tô tay từ frame trống", "frames": [{"frame_idx": 1}]}
        (tmp_path / "index.json").write_text(json.dumps(cu), encoding="utf-8")
        path = gt._viet_index(tmp_path, clip="c.mp4", ten="t", frames=[2], nguoi_gan="A",
                              co_goi_y=True, frame_hw=[40, 50])
        moi = json.loads(path.read_text(encoding="utf-8"))
        assert moi["nguon_gt"] == "người tô tay trên frame gốc"
        assert moi["phuong_phap_gt"] == "tô tay từ frame trống"

    def test_frames_null_khong_lam_chet(self, tmp_path):
        (tmp_path / "index.json").write_text(json.dumps({"dang_gt": "silhouette",
                                                        "frames": None}), encoding="utf-8")
        path = gt._viet_index(tmp_path, clip="c.mp4", ten="t", frames=[7], nguoi_gan="A",
                              co_goi_y=False, frame_hw=[40, 50])
        assert [f["frame_idx"] for f in
                json.loads(path.read_text(encoding="utf-8"))["frames"]] == [7]


class TestGoKhoiGtRong:
    def test_luu_thuong_go_frame_khoi_gt_rong(self, tmp_path):
        """Tô lại một frame từng khai "không có vật" ⇒ index phải GỠ khỏi `gt_rong`."""
        (tmp_path / "index.json").write_text(json.dumps({"gt_rong": [90, 120]}), encoding="utf-8")
        gt._ghi_gt_rong(tmp_path, 90, rong=False)
        index = json.loads((tmp_path / "index.json").read_text(encoding="utf-8"))
        assert index["gt_rong"] == [120]


class TestFramesTraiDeu:
    """Mặc định 12 frame trải đều — để lệnh gán GT KHÔNG còn phải dán dãy số dài.

    Vì sao khoá: 19-11 người dùng dán lệnh có `--frames 0,25,50,57,69,90,105,171,190,230,245,258`
    (dài ~50 ký tự) và terminal chèn **xuống dòng** ngay sau `--frames` ⇒ `bash: argument --frames:
    expected one argument` + `0,25,...: command not found`. Lần 2 liền. Lệnh ngắn là cách chống.
    """

    def test_12_moc_gom_dau_va_cuoi_khong_trung(self):
        from scripts.gt_gan_nhanh import frames_trai_deu

        moc = frames_trai_deu(333)
        assert len(moc) == 12
        assert moc[0] == 0 and moc[-1] == 332
        assert len(set(moc)) == 12 and moc == sorted(moc)

    def test_clip_ngan_hon_so_moc_thi_lay_het_khong_trung(self):
        from scripts.gt_gan_nhanh import frames_trai_deu

        assert frames_trai_deu(5) == [0, 1, 2, 3, 4]
        moc = frames_trai_deu(13)          # `set` chống trùng khi 13 frame mà 12 mốc
        assert len(set(moc)) == len(moc) and moc[0] == 0 and moc[-1] == 12

    def test_clip_khong_doc_duoc_thi_tra_rong(self):
        """0 = không đọc được ⇒ bên gọi phải báo lỗi rõ, KHÔNG được im lặng tạo GT rỗng."""
        from scripts.gt_gan_nhanh import frames_trai_deu

        assert frames_trai_deu(0) == [] and frames_trai_deu(-3) == []


# --- chọn frame "GIỮA KHE" (thay cho dãy --frames dài, xem lý do trong scripts/gt_gan_nhanh.py) ---
def test_frames_giua_khe_dung_dong_du_va_cach_deu():
    """Golden: dãy mốc của binh1 (333 frame, ve=3). Đổi công thức ⇒ test này đỏ CÓ CHỦ Ý.

    Đây là bản golden DUY NHẤT của dãy mốc; test ghép `--khung` bên dưới suy ra từ đây.
    """
    from scripts.gt_gan_nhanh import frames_giua_khe
    ra = frames_giua_khe(333, n=12, vos_every=3)
    assert ra == [2, 32, 62, 92, 122, 152, 182, 212, 242, 272, 302, 332]
    assert all(f % 3 == 2 for f in ra)     # ≡ ve-1 ⇒ CHẮC CHẮN không phải frame VOS


def test_frames_giua_khe_khong_bao_gio_dung_vao_frame_co_vos():
    """Nếu lọt frame chia hết cho vos_every thì ô là của MODEL, không phải LK ⇒ mất ý nghĩa phép đo.

    `assert ra` là BẮT BUỘC: thiếu nó thì hàm trả [] làm vòng `for` không chạy ⇒ test xanh rỗng
    (review độc lập 20-11 chỉ đúng). Thêm ve=7/11/12/20 để khoá luôn hành vi làm tròn bước
    (ve=7 ⇒ 28, ve=11 ⇒ 33, ve=12 ⇒ 24, ve=20 ⇒ 40 — bước phải là bội của ve, không phải luôn 30).
    """
    from scripts.gt_gan_nhanh import frames_giua_khe
    for ve in (2, 3, 4, 5, 7, 11, 12, 20):
        ra = frames_giua_khe(200, n=8, vos_every=ve)
        assert ra, f"ve={ve} trả rỗng — test sẽ xanh rỗng"
        assert all(f % ve == ve - 1 for f in ra), (ve, ra)


def test_frames_giua_khe_bien_vo_huong():
    from scripts.gt_gan_nhanh import frames_giua_khe
    assert frames_giua_khe(0) == []
    assert frames_giua_khe(-5) == []
    assert frames_giua_khe(333, n=0) == []
    # vos_every < 2 ⇒ không có "khe" nào (mọi frame đều do model) ⇒ trả rỗng, KHÔNG rơi về mặc định
    assert frames_giua_khe(333, vos_every=1) == []
    # clip ngắn hơn bước nhảy: vẫn phải ra frame đầu tiên hợp lệ
    assert frames_giua_khe(3, vos_every=3) == [2]
    assert frames_giua_khe(2, vos_every=3) == []


def test_parse_khung():
    from scripts.gt_gan_nhanh import parse_khung
    assert parse_khung("0:110,165:262") == [(0, 110), (165, 262)]
    assert parse_khung(" 0 : 110 ; 165:262 ") == [(0, 110), (165, 262)]
    assert parse_khung("5:5") == [(5, 5)]          # khung 1 frame vẫn hợp lệ
    for xau in ("0-110", "110:0", "-1:5", "", " , "):
        try:
            parse_khung(xau)
        except ValueError:
            continue
        raise AssertionError(f"phải báo lỗi với {xau!r}")


def test_giua_khe_cong_khung_binh1_ra_dung_7_moc():
    """Đúng bộ mốc đã dùng cho binh1 — nếu đổi công thức thì test này phải đổi theo."""
    from scripts.gt_gan_nhanh import frames_giua_khe, parse_khung
    frames = [f for f in frames_giua_khe(333, n=12, vos_every=3)
              if any(a <= f <= b for a, b in parse_khung("0:110,165:262"))]
    assert frames == [2, 32, 62, 92, 182, 212, 242]
    assert all(f % 3 == 2 for f in frames)      # vẫn giữa khe: ô hoàn toàn do LK


# --- `loc_theo_khung`: khoá HỒI QUY lỗi "lọc trước khi sinh danh sách" (20-11) + lỗi ra traceback ---
def test_loc_theo_khung_loc_sau_khi_sinh_va_giu_hai_dau():
    from scripts.gt_gan_nhanh import loc_theo_khung
    # 2, 32, 92 nằm trong 0:110 — KHÔNG được lọc trước khi có danh sách (bản đầu lọc trước ⇒ luôn rỗng)
    assert loc_theo_khung([2, 32, 92, 182, 242], "0:110,165:262") == [2, 32, 92, 182, 242]
    assert loc_theo_khung([0, 110], "0:110") == [0, 110]      # gồm CẢ HAI đầu
    assert loc_theo_khung([7], "7:7") == [7]                  # khung 1 frame
    assert loc_theo_khung([5, 6], None) == [5, 6]             # không khung ⇒ nguyên vẹn
    assert loc_theo_khung([], None) == []


def test_loc_theo_khung_giao_rong_thi_LOI_chu_khong_roi_ve_mac_dinh():
    """Rơi về bộ 12-frame-trải-đều là bẫy: người dùng tưởng đang chấm frame giữa khe, thực ra lẫn cả
    frame CÓ VOS ⇒ phép đo max_mad vô nghĩa mà không ai biết (P1 review độc lập 20-11)."""
    from scripts.gt_gan_nhanh import loc_theo_khung
    with pytest.raises(SystemExit):
        loc_theo_khung([100, 200], "0:50")


def test_loc_theo_khung_chuoi_sai_ra_LOI_chu_khong_phai_traceback():
    """`--khung` là thứ người dùng GÕ TAY; ValueError thô = traceback Python = UX hỏng."""
    from scripts.gt_gan_nhanh import loc_theo_khung
    # `pytest.raises(SystemExit)` đã chứng minh không lọt ValueError thô: SystemExit bắt được còn
    # ValueError thì test sẽ đỏ. (Bản trước gọi thêm lần hai để "kiểm ValueError" — chính lần gọi đó
    # làm SystemExit bắn ra ngoài và test đỏ.)
    for xau in ("110:0", "1:2:3", "0:110 165:262", "-1:5"):
        with pytest.raises(SystemExit):
            loc_theo_khung([1], xau)


# --- P1 review: CLI không được ÂM THẦM rơi về bộ frame mặc định ---
def test_main_tu_choi_vos_every_1_khi_dung_giua_khe(tmp_path, monkeypatch):
    """`--vos-every 1` = đúng cấu hình phiên mIoU của repo ⇒ rất dễ gặp. Hàm thuần trả [] nên CLI
    phải BÁO LỖI, không được lặng lẽ đổi sang 12 frame trải đều (frame đó lẫn frame có VOS)."""
    from scripts import gt_gan_nhanh as gt
    monkeypatch.setattr(gt, "GT_DIR", tmp_path)
    with pytest.raises(SystemExit) as loi:
        gt.main(["--clip", "khong_ton_tai.mp4", "--ten", "t1", "--nguoi-gan", "x",
                 "--giua-khe", "--vos-every", "1"])
    assert "vos-every" in str(loi.value)
    assert not (tmp_path / "t1").exists(), "không được tạo thư mục GT khi đã báo lỗi"


def test_main_tu_choi_giua_khe_0(tmp_path, monkeypatch):
    from scripts import gt_gan_nhanh as gt
    monkeypatch.setattr(gt, "GT_DIR", tmp_path)
    with pytest.raises(SystemExit):
        gt.main(["--clip", "khong_ton_tai.mp4", "--ten", "t2", "--nguoi-gan", "x", "--giua-khe", "0"])
