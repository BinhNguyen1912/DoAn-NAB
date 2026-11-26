"""Test cho đường dựng dataset verifier + số học AUC (`scripts/build_verifier_dataset.py`,
`scripts/train_verifier.py`).

Vì sao có test riêng: dataset này là **đầu vào của một thử nghiệm có thể dẫn tới việc sửa pipeline**.
Ba loại lỗi phải bị chặn bằng máy, vì mắt không thấy:
  1. tách train/val theo FRAME ⇒ điểm val đẹp giả (frame trong một phiên gần trùng nhau);
  2. nhãn "dòng đầu thắng" thay vì "dòng cuối thắng" ⇒ lấy nhãn cũ của bước đã sửa;
  3. bịa ô của hệ khi CSV cũ (trước 21-11) không có `bbox_w/bbox_h`.
"""
from __future__ import annotations

import importlib.util
import json
import pathlib
import sys

import numpy as np
import pytest

REPO = pathlib.Path(__file__).resolve().parent.parent


def _nap(ten: str, duong: pathlib.Path):
    spec = importlib.util.spec_from_file_location(ten, duong)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[ten] = mod
    spec.loader.exec_module(mod)
    return mod


build = _nap("build_verifier_dataset", REPO / "scripts" / "build_verifier_dataset.py")
train = _nap("train_verifier", REPO / "scripts" / "train_verifier.py")


class TestAuc:
    def test_tach_hoan_hao_bang_1(self):
        assert train.auc([0, 0, 1, 1], [0.1, 0.2, 0.8, 0.9]) == 1.0

    def test_dao_nguoc_bang_0(self):
        assert train.auc([0, 0, 1, 1], [0.9, 0.8, 0.2, 0.1]) == 0.0

    def test_hoa_hoan_toan_bang_0_5(self):
        """Mọi điểm bằng nhau ⇒ AUC = 0,5 (hạng trung bình). Bẫy: `argsort` không xử lý hoà sẽ ra 1,0."""
        assert train.auc([0, 1, 0, 1], [0.5] * 4) == 0.5

    def test_diem_nan_tra_nan(self):
        """Model phân kỳ ⇒ điểm NaN. Bản cũ xếp NaN xuống cuối và trả AUC 0,75 'trông hợp lệ'."""
        v = train.auc([0, 1, 0, 1], [0.1, float("nan"), 0.3, 0.9])
        assert v != v, "NaN trong điểm phải ra NaN, không được ra số"

    def test_bootstrap_theo_NHOM_rong_hon_theo_dong(self):
        """Bootstrap theo DÒNG cho CI hẹp giả khi các frame trong một phiên phụ thuộc nhau.

        Đây là tính chất mà docstring/log của script bán — phải có test, nếu không ai đổi sang
        resample từng dòng thì cả bộ test vẫn xanh (review độc lập 26-11).
        """
        rng = np.random.default_rng(0)
        # 4 "phiên", mỗi phiên 20 frame: trong phiên điểm gần như trùng nhau (tương quan cao)
        diem, y, nhom = [], [], []
        for g, nen in enumerate([0.1, 0.1, 0.9, 0.9]):
            for k in range(20):
                nhom.append(f"p{g}")
                y.append(1 if (g % 2 == 0) else 0)      # phiên 0,2 dương; 1,3 âm
                diem.append(nen + rng.normal(0, 0.005))
        theo_nhom = train.auc_theo_cum(y, diem, nhom, n_lan=300, seed=0)
        theo_dong = train.auc_theo_cum(y, diem, list(range(len(y))), n_lan=300, seed=0)
        rong = lambda d: d["ci95"][1] - d["ci95"][0]     # noqa: E731
        assert rong(theo_nhom) > rong(theo_dong), (
            f"CI theo nhóm phải RỘNG hơn theo dòng: {theo_nhom['ci95']} vs {theo_dong['ci95']}")

    def test_mot_lop_tra_nan(self):
        """Thiếu lớp âm ⇒ NaN, KHÔNG được trả 0,5 rồi bị đọc thành 'model đạt 50 %'."""
        v = train.auc([1, 1, 1], [0.1, 0.5, 0.9])
        assert v != v

    def test_ci_chua_diem_va_tat_dinh(self):
        y = np.array([0, 1] * 20)
        diem = np.linspace(0, 1, 40)
        nhom = np.array([f"p{i % 4}" for i in range(40)])
        a = train.auc_theo_cum(y, diem, nhom, n_lan=50, seed=7)
        b = train.auc_theo_cum(y, diem, nhom, n_lan=50, seed=7)
        assert a == b, "cùng seed phải ra cùng số (artifact tái lập được)"
        assert a["ci95"][0] <= a["auc"] <= a["ci95"][1]

    def test_auc_tung_phien_bo_qua_phien_thieu_lop(self):
        """AUC gộp trộn nền nhiều phiên với âm của vài phiên (rò rỉ MIỀN) ⇒ phải có số theo phiên.

        Phiên chỉ có dương không chấm được ⇒ `auc=None` và KHÔNG được tính vào trung bình.
        """
        y = np.array([0, 0, 1, 1, 1, 1])
        diem = np.array([0.1, 0.2, 0.8, 0.9, 0.3, 0.4])
        nhom = np.array(["a", "a", "a", "a", "b", "b"])
        kq = train.auc_tung_phien(y, diem, nhom)
        assert kq["tung_phien"]["a"]["auc"] == 1.0
        assert kq["tung_phien"]["b"] == {"n": 2, "am": 0, "duong": 2, "auc": None}
        assert kq["so_phien_co_hai_lop"] == 1
        assert kq["auc_trung_binh_phien"] == 1.0, "phiên thiếu lớp không được kéo trung bình"

    def test_auc_tung_phien_phoi_bay_so_phien_cham_duoc(self):
        """`so_phien_co_hai_lop` phải lộ ra chuyện "chỉ 2 phiên chấm được" — nếu không, người đọc
        tưởng `auc_trung_binh_phien` là trung bình trên 6 phiên val (thực tế 4 phiên không có âm).
        """
        y = np.array([0, 1, 1, 1, 1, 1])
        nhom = np.array(["a", "a", "b", "b", "c", "c"])   # chỉ phiên 'a' có âm
        diem = np.array([0.2, 0.9, 0.9, 0.95, 0.9, 0.8])
        kq = train.auc_tung_phien(y, diem, nhom)
        assert kq["so_phien_co_hai_lop"] == 1, "phải đếm đúng số phiên CHẤM ĐƯỢC"
        assert kq["auc_trung_binh_phien"] == kq["tung_phien"]["a"]["auc"]
        assert kq["tung_phien"]["b"]["auc"] is None and kq["tung_phien"]["c"]["auc"] is None
        # gộp vẫn ra 1,0 (mọi dương đều trên âm duy nhất) — đúng cái làm người đọc tưởng "hoàn hảo"
        # trong khi chỉ chấm được MỘT phiên. Đây là lý do artifact phải in cả hai con số.
        assert train.auc(y, diem) == 1.0

    def test_cong_chan_so_khong_cong_bo_duoc(self):
        """`kiem_tra_so` phải CHẶN: NaN, val không có âm, None — nếu không, artifact ghi `NaN`."""
        ok = {"val_auc": [0.8, 0.7], "val_auc_trung_binh": 0.75, "so_mau": {"val_am": 57}}
        assert train.kiem_tra_so(ok) == []

        assert train.kiem_tra_so({"val_auc": [float("nan")], "val_auc_trung_binh": 0.5,
                                  "so_mau": {"val_am": 5}}), "NaN phải bị chặn"
        assert train.kiem_tra_so({"val_auc": [0.8], "val_auc_trung_binh": 0.8,
                                  "so_mau": {"val_am": 0}}), "val 0 âm ⇒ AUC vô nghĩa, phải chặn"
        assert train.kiem_tra_so({"val_auc": [], "val_auc_trung_binh": None,
                                  "so_mau": {"val_am": 5}}), "thiếu số phải bị chặn"
        assert train.kiem_tra_so({"val_auc": [0.8], "val_auc_trung_binh": float("nan"),
                                  "so_mau": {"val_am": 3}}), "TB NaN phải bị chặn"

    def test_model_eval_tat_dinh(self):
        """`eval()` phải cho cùng output cho cùng input; `chay_mot_seed` còn raise nếu lệch."""
        import torch as th
        m = train.Verifier().eval()
        x = th.zeros(2, 3, 64, 64)
        with th.no_grad():
            a, b = m(x).numpy(), m(x).numpy()
        assert np.array_equal(a, b)
        import inspect
        assert "model.eval() không tất định" in inspect.getsource(train.chay_mot_seed), \
            "phải ASSERT (raise), không chỉ ghi số như bản đầu"

    def test_ngong_dung_do_lech_chuan(self, tmp_path):
        tron = tmp_path / "tron.jpg"
        import cv2
        cv2.imwrite(str(tron), np.full((32, 32, 3), 128, np.uint8))       # phẳng ⇒ std = 0
        co = tmp_path / "co.jpg"
        rng = np.random.default_rng(0)
        cv2.imwrite(str(co), rng.integers(0, 255, (32, 32, 3), dtype=np.uint8))
        assert train.dac_trung_ngong(tron) < 1.0
        assert train.dac_trung_ngong(co) > 20.0


class TestHoTro:
    def test_noi_o_kep_va_tra_rong_khi_suy_bien(self):
        assert build.noi_o([10, 10, 20, 20], 100, 100, 0.0) == (10, 10, 20, 20)
        x1, y1, x2, y2 = build.noi_o([0, 0, 100, 100], 100, 100, 0.5)
        assert (x1, y1, x2, y2) == (0, 0, 100, 100), "nới ra ngoài khung phải KẸP, không tràn"
        # ô 1px: nội dung không đủ để phóng lên 64×64 ⇒ bỏ (đếm vào `bo_qua['<loại>-ô-rỗng']`)
        assert build.noi_o([5, 5, 6, 6], 100, 100, 0.0) == (0, 0, 0, 0)
        assert build.noi_o([-50, -50, -49, -49], 100, 100, 0.0) == (0, 0, 0, 0), "ô ngoài khung ⇒ bỏ"

    def test_nhan_dong_CUOI_thang(self):
        """Nhãn append-only: dòng CUỐI là nhãn hiệu lực (khớp `--tong-hop`), không phải dòng đầu."""
        import tempfile
        with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False,
                                         encoding="utf-8") as f:
            for nhan in ("dung", "sai", "dung"):
                f.write(json.dumps({"buoc": 7, "nhan": nhan}) + "\n")
            f.write(json.dumps({"buoc": 8, "nhan": "mat_dau"}) + "\n")
            f.write("{dòng hỏng\n")
            ten = f.name
        d = build.doc_nhan_hieu_luc(pathlib.Path(ten))
        assert d[7]["nhan"] == "dung" and d[8]["nhan"] == "mat_dau"
        pathlib.Path(ten).unlink()

    def test_o_he_dang_ve(self):
        assert build.o_he_dang_ve({"bbox": [10, 20, 110, 220]}) == [10, 20, 110, 220]
        # CSV sinh TRƯỚC 21-11 không có bbox_w/bbox_h ⇒ `doc_phien` trả bbox None ⇒ phải là None
        assert build.o_he_dang_ve({"bbox": None}) is None
        assert build.o_he_dang_ve({}) is None
        assert build.o_he_dang_ve({"bbox": [10, 10, 10, 10]}) is None, "ô suy biến không dùng được"
        assert build.o_he_dang_ve({"bbox": [float('nan'), 0, 5, 5]}) is None

    def test_tach_theo_phien_tat_dinh(self):
        a = [build.tach(f"phien{i}", 0.25) for i in range(40)]
        b = [build.tach(f"phien{i}", 0.25) for i in range(40)]
        assert a == b, "chạy lại phải ra cùng split (không phụ thuộc thứ tự/ngày)"
        assert set(a) == {"train", "val"}
        assert build.tach("phien0", 0.0) == "train"
        assert build.tach("phien0", 1.0) == "val"


# ── end-to-end trên fixture tổng hợp ───────────────────────────────────────────────────────────────


def _video(p: pathlib.Path, n: int = 20, fps: float = 10.0):
    import cv2
    w = cv2.VideoWriter(str(p), cv2.VideoWriter_fourcc(*"mp4v"), fps, (64, 48))
    for k in range(n):
        khung = np.zeros((48, 64, 3), np.uint8)
        khung[10:40, 10:50] = (k * 12 % 255, 90, 140)      # vùng "vật" để crop có nội dung
        w.write(khung)
    w.release()
    assert p.is_file() and p.stat().st_size > 0


def _csv(p: pathlib.Path, n: int = 20, co_o: bool = True):
    cot = "frame_idx,latency_ms,center_x,center_y"
    if co_o:
        cot += ",bbox_w,bbox_h"
    dong = [cot + ",mask_area"]
    for k in range(n):
        d = f"{k},100,30,25"
        if co_o:
            d += ",20,25"
        dong.append(d + ",500")
    p.write_text("\n".join(dong) + "\n", encoding="utf-8")


@pytest.fixture()
def fixture(tmp_path, monkeypatch):
    """2 phiên: `moi` (CSV có ô) và `cu` (CSV không có ô, như dữ liệu trước 21-11)."""
    import src.worker as W
    from tools import label_ui as L

    data = tmp_path / "data"
    nhan = data / "nhan"
    nhan.mkdir(parents=True)
    for ten, co_o in (("moi_phien", True), ("cu_phien", False)):
        _video(data / f"{ten}.mp4")
        _csv(data / f"{ten}_metrics.csv", co_o=co_o)
    (nhan / "moi_phien.jsonl").write_text("\n".join(json.dumps(r) for r in [
        {"buoc": 0, "nhan": "dung"},
        {"buoc": 1, "nhan": "sai", "bbox_dung": [10, 10, 50, 40]},
        {"buoc": 2, "nhan": "sai"},
        {"buoc": 3, "nhan": "khong_co_vat"},
        {"buoc": 4, "nhan": "dung"},          # dòng sau sửa lại thành 'sai' ⇒ chỉ tính 'sai'
        {"buoc": 4, "nhan": "sai"},
    ]) + "\n", encoding="utf-8")
    (nhan / "cu_phien.jsonl").write_text("\n".join(json.dumps(r) for r in [
        {"buoc": 0, "nhan": "dung"},
        {"buoc": 1, "nhan": "sai", "bbox_dung": [12, 12, 48, 38]},
    ]) + "\n", encoding="utf-8")

    monkeypatch.setattr(build, "DATA", data)
    monkeypatch.setattr(build, "NHAN", nhan)
    monkeypatch.setattr(L, "DATA_DIR", data)
    monkeypatch.setattr(L, "THU_MUC_NHAN", nhan)
    monkeypatch.setattr(L, "_CAP", {})
    monkeypatch.setattr(W, "transcode_for_web", lambda *a, **k: None)
    return tmp_path, data, nhan


class TestDungDataset:
    def test_sinh_mau_dung_loai(self, fixture):
        tmp_path, _, _ = fixture
        kq = build.dung_dataset(tmp_path / "out", 0.25, 0.15)
        # moi_phien: buoc0 dung⇒pos_sys; buoc1 sai⇒neg_sys + pos_gt; buoc2 sai⇒neg_sys;
        #            buoc4 (sửa 'dung'→'sai') ⇒ neg_sys
        # cu_phien:  KHÔNG có ô của hệ (CSV trước 21-11) ⇒ CHỈ pos_gt, không được bịa ô
        assert kq["theo_loai"] == {"pos_sys": 1, "neg_sys": 3, "pos_gt": 2}, kq["theo_loai"]
        assert kq["theo_nhan"] == {1: 3, 0: 3}, kq["theo_nhan"]   # khoá là SỐ (nhãn 0/1)
        assert kq["bo_qua"].get("khong_co_vat") == 1
        assert kq["cat_loi"] == 0

    def test_anh_cat_ton_tai_va_dung_co(self, fixture):
        import cv2
        tmp_path, _, _ = fixture
        kq = build.dung_dataset(tmp_path / "out", 0.25, 0.15)
        assert kq["so_mau"] == 6
        for d in (tmp_path / "out").rglob("*.jpg"):
            assert cv2.imread(str(d)).shape == (64, 64, 3)
        assert len(kq["theo_split"]) >= 1

    def test_mot_phien_khong_nam_o_ca_hai_split(self, fixture):
        tmp_path, _, _ = fixture
        kq = build.dung_dataset(tmp_path / "out", 0.5, 0.15)
        man = [json.loads(x) for x in
               (tmp_path / "out" / "manifest.jsonl").read_text(encoding="utf-8").splitlines() if x]
        assert man, "manifest không được rỗng"
        theo: dict[str, set] = {}
        for m in man:
            theo.setdefault(m["phien"], set()).add(m["split"])
        assert all(len(v) == 1 for v in theo.values()), f"rò rỉ split: {theo}"
        assert sum(kq["theo_split"].values()) == kq["so_mau"]

    def test_nhan_dong_cuoi_duoc_dung(self, fixture):
        """Bước 4 khai 'dung' rồi 'sai' ⇒ phải sinh `neg_sys`, không phải `pos_sys`."""
        tmp_path, _, _ = fixture
        build.dung_dataset(tmp_path / "out", 0.25, 0.15)
        man = [json.loads(x) for x in
               (tmp_path / "out" / "manifest.jsonl").read_text(encoding="utf-8").splitlines() if x]
        b4 = [m for m in man if m["phien"] == "moi_phien" and m["buoc"] == 4]
        assert [m["loai"] for m in b4] == ["neg_sys"], b4
        assert b4[0]["nhan"] == 0

    def test_dem_ly_do_bi_bo(self, fixture):
        """Không đếm thì không ai audit được "vì sao chỉ có 414 âm" (review 26-11).

        `cu_phien` (CSV cũ) có 1 bước `dung` + 1 bước `sai` mà CSV KHÔNG có ô của hệ ⇒ phải lộ ra.
        """
        tmp_path, _, _ = fixture
        kq = build.dung_dataset(tmp_path / "out", 0.25, 0.15)
        assert kq["bo_qua"].get("dung-khong-co-o-he") == 1, kq["bo_qua"]
        assert kq["bo_qua"].get("sai-khong-co-o-he") == 1, kq["bo_qua"]

    def test_phien_khong_ra_mau_nao_duoc_bao(self, fixture):
        tmp_path, data, nhan = fixture
        (nhan / "trong.jsonl").write_text(
            json.dumps({"buoc": 0, "nhan": "khong_co_vat"}) + "\n", encoding="utf-8")
        import src.worker as W
        from tools import label_ui as L
        import shutil
        shutil.copy(data / "moi_phien.mp4", data / "trong.mp4")
        shutil.copy(data / "moi_phien_metrics.csv", data / "trong_metrics.csv")
        _ = (W, L)
        kq = build.dung_dataset(tmp_path / "out", 0.25, 0.15)
        assert "trong" in kq["phien_0_mau"], kq["phien_0_mau"]

    def test_doi_margin_phai_cat_lai_anh(self, fixture):
        """Cache ảnh khoá `{loai}_b{buoc}` ⇒ đổi `--margin` mà không xoá cache là
        **ảnh cũ + artifact ghi tham số mới** (review 26-11, P2)."""
        tmp_path, _, _ = fixture
        kq1 = build.dung_dataset(tmp_path / "out", 0.25, 0.0)
        assert kq1["da_xoa_cache_cu"] is False
        goc = [p.stat().st_size for p in sorted((tmp_path / "out").rglob("*.jpg"))]
        kq2 = build.dung_dataset(tmp_path / "out", 0.25, 0.5)
        assert kq2["da_xoa_cache_cu"] is True, "vân tay đổi ⇒ phải xoá cache cũ"
        moi = [p.stat().st_size for p in sorted((tmp_path / "out").rglob("*.jpg"))]
        assert moi and moi != goc, "margin đổi ⇒ ảnh phải được cắt LẠI (nội dung khác)"
        assert kq2["dau_van_tay"] != kq1["dau_van_tay"]

    def test_phien_co_hai_nguoi_dan_duoc_bao(self, fixture):
        """Gộp nhãn 'dòng cuối thắng' bỏ người dán ⇒ phải LỘ ra khi một phiên có >1 người."""
        tmp_path, data, nhan = fixture
        # Hai BƯỚC có nhãn hiệu lực của HAI người khác nhau (dòng cuối mỗi bước thắng)
        rows = [{"buoc": 0, "nhan": "dung", "nguoi_gan": "binh"},
                {"buoc": 2, "nhan": "sai", "nguoi_gan": "nguoi_thu_hai"}]
        (nhan / "moi_phien.jsonl").write_text(
            "\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
        kq = build.dung_dataset(tmp_path / "out", 0.25, 0.15)
        assert sorted(kq["phien_nhieu_nguoi_dan"].get("moi_phien", [])) == ["binh", "nguoi_thu_hai"], \
            kq["phien_nhieu_nguoi_dan"]

    def test_phien_thieu_video_bi_bao_khong_im_lang(self, fixture):
        """Thiếu nguồn ⇒ phải nêu tên phiên, KHÔNG được lặng lẽ ra dataset nhỏ hơn."""
        tmp_path, data, _ = fixture
        (data / "moi_phien.mp4").unlink()
        kq = build.dung_dataset(tmp_path / "out", 0.25, 0.15)
        assert any("moi_phien" in x for x in kq["phien_thieu_video"]), kq["phien_thieu_video"]


class TestArtifact:
    def test_artifact_co_provenance(self, fixture, tmp_path, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["build_verifier_dataset.py", "--out",
                                          str(tmp_path / "out"),
                                          "--metrics", str(tmp_path / "m.json")])
        assert build.main() == 0
        d = json.loads((tmp_path / "m.json").read_text(encoding="utf-8"))
        for k in ("do_luc", "lenh", "git_rev", "git_dirty", "git_dirty_code", "chiet_giai"):
            assert k in d, f"artifact thiếu `{k}` (AGENTS §6)"
        assert d["so_mau"] == 6
