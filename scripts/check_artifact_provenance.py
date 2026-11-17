"""Kiểm `git_rev` khai trong artifact số đo có còn tồn tại trong lịch sử repo.

Vì sao cần: hôm nay repo đã **ba lần** dẫn một `git_rev` đã chết (rebase/squash/artifact bị sinh lại
đè) trong tài liệu, ticket và log — người đọc không tái lập được số và không ai biết. `data/*_metrics.json`
là bằng chứng của báo cáo, nên provenance của nó phải kiểm bằng máy, không bằng mắt.

Ba trạng thái, KHÔNG gộp:
- `ok`   — rev là tổ tiên (ancestor) của `HEAD` ⇒ số đo thuộc cây đang có.
- `lech` — rev CÒN tồn tại nhưng không phải tổ tiên của `HEAD` (nhánh chưa merge, commit đã bị
           thay bằng rebase) ⇒ số đo thuộc cây khác; **cảnh báo**, không chặn (artifact cũ hợp lệ).
- `chet` — rev không tồn tại ⇒ không ai lấy lại được mã đã sinh ra số đó: **chặn** (mã thoát 1).

Cách dùng:
    python scripts/check_artifact_provenance.py            # quét `data/*_metrics.json`
    python scripts/check_artifact_provenance.py --gioi-han-lui 3   # chỉ xét artifact đổi trong N commit
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]

# `git_rev` ĐÃ CHẾT nhưng artifact giữ nguyên (không sửa tay bằng chứng đã commit) — mỗi mục phải nêu
# LÝ DO. Có danh sách này thì `--nghiem` vẫn bắt được rev chết MỚI (đúng lớp lỗi repo gặp 3 lần hôm nay)
# mà CI không đỏ vì nợ lịch sử.
CHO_PHEP = {
    ("drift_2026-11-08_metrics.json", "ee9f256a1e77e6b4de08b0b0b8f4b0f0b8f0b0b8"):
        "rev không tồn tại trong repo (nghi gõ tay lúc ghi artifact 08-11); số đo vẫn dùng được nhưng "
        "CẤM dẫn rev này — xem `docs/task/08-11-2026-do-cai-gia-noi-suy-lk-va-nguong-nhieu.md`",
    # Hai artifact 10-11 đo từ relay webcam THẬT (không sinh lại được nếu không có camera đúng thời
    # điểm) nhưng rev chỉ tồn tại trong object LOCAL — nhánh bị rebase trước khi push, nên trên remote
    # `git cat-file -e` thất bại. Số trong `docs/doi-chieu-yeu-cau-gvhd.md` vẫn dùng được (đo thật),
    # chỉ là không truy được về commit ⇒ CẤM dẫn rev.
    ("empty_window_2026-11-10_metrics.json", "eb008e3d414d1c4406cc641a1c3a703303017243"):
        "rev chỉ có trong object local (nhánh rebase trước khi push) — số thật 10-11, CẤM dẫn rev",
    ("live_web_relay_2026-11-10_metrics.json", "da1d671c3c20be6f98ea4a3f4674714ff1fdae6c"):
        "rev chỉ có trong object local (nhánh rebase trước khi push) — số relay webcam thật 10-11, "
        "CẤM dẫn rev",
}


def _git(*args: str) -> tuple[int, str]:
    p = subprocess.run(["git", *args], cwd=_REPO_ROOT, capture_output=True, text=True)
    return p.returncode, (p.stdout or p.stderr).strip()


def phan_loai(rev: str | None) -> str:
    """`ok` / `lech` / `chet` — xem docstring đầu file."""
    if not rev:
        return "chet"                      # không khai rev = không truy được về đâu cả
    rc, _ = _git("cat-file", "-e", f"{rev}^{{commit}}")
    if rc != 0:
        return "chet"
    rc, _ = _git("merge-base", "--is-ancestor", rev, "HEAD")
    return "ok" if rc == 0 else "lech"


def quet(thu_muc: Path, cho_phep=None) -> list[dict]:
    """Mỗi artifact `*_metrics.json` → `{file, git_rev, trang_thai, ghi_chu}`.

    `trang_thai` ∈ `ok` / `lech` / `chet` / `ok-da-biet` (chết nhưng nằm trong `CHO_PHEP`).
    """
    cho_phep = CHO_PHEP if cho_phep is None else cho_phep
    ra = []
    for f in sorted(thu_muc.glob("*_metrics.json")):
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            ra.append({"file": f.name, "git_rev": None, "trang_thai": "chet",
                       "ghi_chu": "artifact không đọc được"})
            continue
        rev = d.get("git_rev") if isinstance(d, dict) else None
        trang_thai = phan_loai(rev)
        ghi_chu = None
        if trang_thai == "chet" and (f.name, rev) in cho_phep:
            trang_thai, ghi_chu = "ok-da-biet", cho_phep[(f.name, rev)]
        ra.append({"file": f.name, "git_rev": rev, "trang_thai": trang_thai, "ghi_chu": ghi_chu})
    return ra


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Kiểm git_rev trong data/*_metrics.json.")
    ap.add_argument("--thu-muc", default=None, help="thư mục artifact (mặc định `data/`)")
    ap.add_argument("--nghiem", action="store_true",
                    help="thoát 1 nếu có `git_rev` chết MỚI (rev trong `CHO_PHEP` không tính)")
    args = ap.parse_args(argv)
    thu_muc = Path(args.thu_muc) if args.thu_muc else (_REPO_ROOT / "data")
    if not thu_muc.is_dir():
        print(f"[provenance] không có thư mục {thu_muc}")
        return 2

    ket_qua = quet(thu_muc)
    if not ket_qua:
        print(f"[provenance] {thu_muc} không có artifact nào — không phải 'đã kiểm' (AGENTS §6)")
        return 0

    chet = [r for r in ket_qua if r["trang_thai"] == "chet"]
    lech = [r for r in ket_qua if r["trang_thai"] == "lech"]
    da_biet = [r for r in ket_qua if r["trang_thai"] == "ok-da-biet"]
    for r in ket_qua:
        if r["trang_thai"] == "ok":
            continue                                   # im lặng cho 44 artifact bình thường
        rev = (r["git_rev"] or "")[:7] or "—"
        print(f"{r['trang_thai']:11} {r['file']:52} {rev}")
        if r["ghi_chu"]:
            print(f"            └ {r['ghi_chu']}")
    print(f"\n[provenance] {len(ket_qua)} artifact: "
          f"{len(ket_qua) - len(chet) - len(lech) - len(da_biet)} ok · {len(lech)} lệch · "
          f"{len(da_biet)} chết-đã-biết · {len(chet)} CHẾT-MỚI")
    if chet and not args.nghiem:
        print("[provenance] cảnh báo: có rev chết mới (dùng --nghiem để chặn)", file=sys.stderr)
    if chet:
        print("[provenance] CHẾT = `git_rev` không tồn tại (thường do rebase/squash hoặc artifact bị "
              "sinh lại đè): số đo không tái lập được ⇒ ghi rõ trong tài liệu hoặc sinh lại artifact "
              "trên cây sạch", file=sys.stderr)
        return 1 if args.nghiem else 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
