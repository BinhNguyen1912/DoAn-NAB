#!/usr/bin/env python3
"""Baseline cho BỘ KIỂM "ô hệ đang vẽ có đúng là vật không" (verifier) — đo xem có học được gì.

Câu hỏi cần trả lời (không phải "làm ra sản phẩm"):
    Với nhãn người dán hiện có, một mô hình nhỏ **học được** việc phân biệt *vùng hệ vẽ đúng vật*
    với *vùng hệ bám sai* không? Nếu AUC ≈ 0,5 thì đường "verifier" này chết và phải tìm cách khác
    (đo trước, hứa sau — AGENTS §6).

Vì sao là mô hình NHỎ + split theo phiên
----------------------------------------
Máy này không có GPU (chỉ Iris Xe, `torch` bản CPU) và dataset chỉ ~3 000 ảnh 64×64. Mô hình lớn hơn
không đo được gì thêm. Split **theo phiên** (`scripts/build_verifier_dataset.py`) nên điểm val không
phải "nhớ ảnh": các frame trong một phiên gần trùng nhau.

Ba con số phải đọc cùng nhau
----------------------------
1. `val.auc`        — khả năng xếp hạng trên phiên CHƯA thấy;
2. `val.ci95`       — bootstrap theo **phiên val** (không theo frame: frame trong một phiên phụ thuộc);
3. `auc_trivial_*`  — AUC của bộ phân loại NGỐ chỉ dùng độ tương phản ảnh cắt.
   `val.auc` không vượt rõ con số đó ⇒ mô hình chỉ học "vùng trơn = sai", đúng cái mẹo `pos_gt` sinh
   ra để chặn.

`--seeds 0,1,2` (mặc định) để artifact có `mean ± std`: một lần chạy (n=1) không cho phép kết luận gì.

    python scripts/train_verifier.py                       # 3 seed, 12 epoch
    python scripts/train_verifier.py --seeds 0 --epochs 20
"""
from __future__ import annotations

import argparse
import json
import pathlib
import random
import subprocess
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import cv2  # noqa: E402
import numpy as np  # noqa: E402
import torch  # noqa: E402
import torch.nn as nn  # noqa: E402


def git(*args: str) -> str:
    try:
        return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True,
                              check=False).stdout.strip()
    except OSError:
        return ""


# ── số học: AUC + bootstrap (tự viết để không thêm phụ thuộc; sklearn KHÔNG có trong môi trường) ─────


def auc(y, diem) -> float:
    """AUC theo công thức Mann–Whitney (hoà ⇒ hạng trung bình). NaN khi thiếu một lớp."""
    y = np.asarray(y).astype(int)
    diem = np.asarray(diem, dtype=float)
    n1, n0 = int(y.sum()), int((1 - y).sum())
    if n1 == 0 or n0 == 0:
        return float("nan")
    hang = np.empty(len(diem))
    order = np.argsort(diem, kind="mergesort")
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and diem[order[j + 1]] == diem[order[i]]:
            j += 1
        hang[order[i:j + 1]] = (i + j) / 2.0 + 1.0
        i = j + 1
    r1 = hang[y == 1].sum()
    return float((r1 - n1 * (n1 + 1) / 2.0) / (n1 * n0))


def auc_theo_cum(y, diem, nhom, n_lan: int = 1000, seed: int = 0) -> dict:
    """AUC + CI95 bootstrap **theo nhóm** (gom cả một phiên ⇒ giữ tính phụ thuộc giữa các frame)."""
    y, diem, nhom = np.asarray(y), np.asarray(diem), np.asarray(nhom)
    goc = auc(y, diem)
    duy_nhat = np.unique(nhom)
    rng = np.random.default_rng(seed)
    gia = []
    for _ in range(n_lan):
        chon = rng.choice(duy_nhat, size=len(duy_nhat), replace=True)
        idx = np.concatenate([np.flatnonzero(nhom == g) for g in chon])
        v = auc(y[idx], diem[idx])
        if v == v:
            gia.append(v)
    ra = {"auc": round(float(goc), 4), "n": int(len(y)), "so_nhom": int(len(duy_nhat)),
          "so_lan_hop_le": len(gia)}
    ra["ci95"] = ([round(float(np.percentile(gia, 2.5)), 4),
                   round(float(np.percentile(gia, 97.5)), 4)] if gia else None)
    return ra


def auc_tung_phien(y, diem, nhom) -> dict:
    """AUC **trong từng phiên** — chỉ phiên có CẢ hai lớp mới chấm được.

    Vì sao cần: AUC gộp trộn ảnh của 6 phiên dương với âm của 2 phiên ⇒ mô hình có thể chỉ học
    "nền của phiên này = âm" (rò rỉ MIỀN) mà vẫn điểm cao. Trong một phiên, âm và dương cùng nền/cùng
    vật ⇒ đây mới là con số phản ánh việc dùng thật (so sánh trong một buổi quay).
    """
    y, diem, nhom = np.asarray(y), np.asarray(diem), np.asarray(nhom)
    ra, hop_le = {}, []
    for g in sorted(set(nhom.tolist())):
        sel = nhom == g
        a = auc(y[sel], diem[sel])
        ra[str(g)] = {"n": int(sel.sum()), "am": int((y[sel] == 0).sum()),
                      "duong": int((y[sel] == 1).sum()),
                      "auc": (round(float(a), 4) if a == a else None)}
        if a == a:
            hop_le.append(float(a))
    return {"tung_phien": ra, "so_phien_co_hai_lop": len(hop_le),
            "auc_trung_binh_phien": round(float(np.mean(hop_le)), 4) if hop_le else None,
            "auc_min_phien": round(min(hop_le), 4) if hop_le else None}


def dac_trung_ngong(path: pathlib.Path) -> float:
    """Bộ phân loại NGỐ: độ lệch chuẩn pixel (vùng trơn ⇒ thấp). Dùng để phát hiện mẹo."""
    anh = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    return float(anh.std()) if anh is not None else 0.0


# ── mô hình ─────────────────────────────────────────────────────────────────────────────────────────


class Verifier(nn.Module):
    """CNN nhỏ: 4 khối conv + global average pooling ⇒ 1 logit (đúng/sai)."""

    def __init__(self) -> None:
        super().__init__()

        def khoi(vao: int, ra: int) -> nn.Sequential:
            return nn.Sequential(nn.Conv2d(vao, ra, 3, padding=1), nn.BatchNorm2d(ra),
                                 nn.ReLU(inplace=True), nn.MaxPool2d(2))

        self.than = nn.Sequential(khoi(3, 16), khoi(16, 32), khoi(32, 64), khoi(64, 96))
        self.dau = nn.Linear(96, 1)

    def forward(self, x):
        return self.dau(self.than(x).mean(dim=(2, 3))).squeeze(1)


def nap_anh(duong: pathlib.Path) -> np.ndarray:
    anh = cv2.imread(str(duong), cv2.IMREAD_COLOR)
    if anh is None:
        return np.zeros((64, 64, 3), np.uint8)
    return cv2.resize(cv2.cvtColor(anh, cv2.COLOR_BGR2RGB), (64, 64), interpolation=cv2.INTER_AREA)


def doc_manifest(p: pathlib.Path, goc: pathlib.Path) -> list[dict]:
    ra = []
    for dong in p.read_text(encoding="utf-8").splitlines():
        if dong.strip():
            m = json.loads(dong)
            m["_anh"] = goc / m["anh"]
            if m["_anh"].is_file():
                ra.append(m)
    return ra


def _tensor(ms: list[dict]) -> tuple[torch.Tensor, torch.Tensor]:
    x = np.stack([nap_anh(m["_anh"]) for m in ms]).astype(np.float32) / 255.0
    x = (x - 0.5) / 0.5
    y = np.array([m["nhan"] for m in ms], np.float32)
    return torch.from_numpy(x).permute(0, 3, 1, 2), torch.from_numpy(y)


def chay_mot_seed(tr: list[dict], va: list[dict], args, seed: int) -> dict:
    """Huấn luyện + đánh giá MỘT seed. Trả dict số (không ghi file) để `main` gộp nhiều seed."""
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)

    xtr, ytr = _tensor(tr)
    xva, yva = _tensor(va)
    n_pos, n_neg = float((ytr == 1).sum()), float((ytr == 0).sum())
    loss_fn = nn.BCEWithLogitsLoss(pos_weight=torch.tensor([n_neg / max(n_pos, 1.0)]))

    model = Verifier()
    opt = torch.optim.Adam(model.parameters(), lr=args.lr)
    t0 = time.time()
    lich = []
    for ep in range(args.epochs):
        model.train()
        thu_tu = torch.randperm(len(xtr))
        tong = 0.0
        for i in range(0, len(thu_tu), args.batch):
            idx = thu_tu[i:i + args.batch]
            opt.zero_grad()
            loss = loss_fn(model(xtr[idx]), ytr[idx])
            loss.backward()
            opt.step()
            tong += loss.item() * len(idx)
        model.eval()
        with torch.no_grad():
            p = torch.sigmoid(model(xva)).numpy()
        lich.append({"epoch": ep + 1, "loss_train": round(tong / len(tr), 4),
                     "auc_val": round(auc(yva.numpy(), p), 4)})

    model.eval()
    with torch.no_grad():
        p_va = torch.sigmoid(model(xva)).numpy()
        p_tr = torch.sigmoid(model(xtr)).numpy()
        mot1 = float(torch.sigmoid(model(xva[:1])).item())
        mot2 = float(torch.sigmoid(model(xva[:1])).item())     # eval ⇒ phải giống hệt lần trước
    nhom = np.array([m["phien"] for m in va])
    ngong = np.array([dac_trung_ngong(m["_anh"]) for m in va])
    return {
        "seed": seed,
        "giay": round(time.time() - t0, 1),
        "val": auc_theo_cum(yva.numpy(), p_va, nhom, seed=seed),
        "train_auc": round(float(auc(ytr.numpy(), p_tr)), 4),
        "ngong": auc_theo_cum(yva.numpy(), ngong, nhom, seed=seed),
        "theo_phien": auc_tung_phien(yva.numpy(), p_va, nhom),
        "mot_anh_lap_lai": [round(mot1, 6), round(mot2, 6)],
        "lich": lich,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", default="data/verifier/manifest.jsonl")
    ap.add_argument("--goc", default="data/verifier", help="thư mục gốc chứa ảnh trong manifest")
    ap.add_argument("--epochs", type=int, default=12)
    ap.add_argument("--batch", type=int, default=64)
    ap.add_argument("--lr", type=float, default=1e-3)
    ap.add_argument("--seeds", default="0,1,2", help="nhiều seed ⇒ artifact có mean ± std")
    ap.add_argument("--metrics", default="data/verifier_baseline_metrics.json")
    args = ap.parse_args()

    torch.set_num_threads(min(8, torch.get_num_threads()))
    goc = ROOT / args.goc
    mau = doc_manifest(ROOT / args.manifest, goc)
    if not mau:
        print("manifest rỗng — chạy scripts/build_verifier_dataset.py trước", file=sys.stderr)
        return 1
    tr = [m for m in mau if m["split"] == "train"]
    va = [m for m in mau if m["split"] == "val"]
    if not tr or not va:
        print(f"thiếu split (train={len(tr)}, val={len(va)})", file=sys.stderr)
        return 1

    seeds = [int(x) for x in args.seeds.split(",") if x.strip()]
    cac_lan = [chay_mot_seed(tr, va, args, sd) for sd in seeds]
    aucs = [c["val"]["auc"] for c in cac_lan]
    ngong = [c["ngong"]["auc"] for c in cac_lan]

    payload = {
        "schema": 1,
        "do_luc": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "lenh": " ".join(sys.argv),
        "git_rev": git("rev-parse", "--short", "HEAD"),
        "git_dirty": bool(git("status", "--porcelain")),
        "git_dirty_code": bool(git("status", "--porcelain", "--", ".", ":!data")),
        "epochs": args.epochs, "batch": args.batch, "lr": args.lr, "seeds": seeds,
        "so_mau": {"train": len(tr), "val": len(va),
                   "val_am": sum(1 for m in va if m["nhan"] == 0),
                   "val_duong": sum(1 for m in va if m["nhan"] == 1),
                   "val_phien": len({m["phien"] for m in va})},
        "val_auc": aucs,
        "val_auc_trung_binh": round(float(np.mean(aucs)), 4),
        "val_auc_std": round(float(np.std(aucs, ddof=1)), 4) if len(aucs) > 1 else None,
        "val_auc_min": min(aucs), "val_auc_max": max(aucs),
        "ngong_auc": ngong,
        "ngong_auc_trung_binh": round(float(np.mean(ngong)), 4),
        "train_auc": [c["train_auc"] for c in cac_lan],
        "cac_lan": [{k: c[k] for k in ("seed", "val", "train_auc", "ngong", "giay")}
                    for c in cac_lan],
        "val_auc_theo_phien": cac_lan[0]["theo_phien"],
        "val_am_theo_phien": {p: v["am"] for p, v in
                              cac_lan[0]["theo_phien"]["tung_phien"].items()},
        "lich_epoch_seed_dau": cac_lan[0]["lich"],
        "diem_mot_anh_lap_lai": cac_lan[0]["mot_anh_lap_lai"],
        "giay": round(sum(c["giay"] for c in cac_lan), 1),
        "chiet_giai": (
            "`ngong_auc` = AUC của bộ phân loại NGỐ chỉ dùng độ lệch chuẩn pixel (vùng trơn ⇒ thấp); "
            "`val_auc` không vượt rõ con số này thì mô hình chỉ học 'tường trơn = sai'. "
            "`val_auc_theo_phien` là con số ĐÚNG ĐỂ ĐỌC: âm và dương cùng một phiên ⇒ không rò rỉ "
            "miền; `val_auc` gộp thì trộn nền của nhiều phiên với âm của vài phiên nên có thể cao/giả. "
            "`val_am_theo_phien` cho thấy âm dồn vào phiên nào — phiên 0 âm thì không chấm được (auc "
            "null). CI95 bootstrap theo PHIÊN val. `val_am` nhỏ ⇒ CI rộng; đọc `val_auc_std` (giữa "
            "seed) trước khi kết luận. Nhãn là phán quyết của MỘT người cho CẢ bước, không phải mask — "
            "hạn chế này phải nêu khi trích số."),
    }
    p = ROOT / args.metrics
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")

    print(json.dumps({"so_mau": payload["so_mau"], "val_auc": aucs,
                      "trung_binh": payload["val_auc_trung_binh"],
                      "std": payload["val_auc_std"], "ngong": ngong,
                      "train_auc": payload["train_auc"], "giay": payload["giay"]},
                     ensure_ascii=False, indent=1))
    print(f"→ {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
