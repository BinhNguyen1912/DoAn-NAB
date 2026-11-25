"""Kiểm `git_rev` khai trong artifact số đo có còn tồn tại trong lịch sử repo.

Vì sao cần: hôm nay repo đã **ba lần** dẫn một `git_rev` đã chết (rebase/squash/artifact bị sinh lại
đè) trong tài liệu, ticket và log — người đọc không tái lập được số và không ai biết. `data/*_metrics.json`
là bằng chứng của báo cáo, nên provenance của nó phải kiểm bằng máy, không bằng mắt.

Ba trạng thái (`ok`/`lech`/`chet`) + MỘT nhãn hạ allowlist (`ok-da-biet`), KHÔNG gộp:
- `ok`   — rev là tổ tiên (ancestor) của `HEAD` ⇒ số đo thuộc cây đang có.
- `lech` — rev CÒN tồn tại nhưng không phải tổ tiên của `HEAD` (nhánh chưa merge, commit đã bị
           thay bằng rebase) ⇒ số đo thuộc cây khác; **cảnh báo**, không chặn (artifact cũ hợp lệ).
- `chet` — rev không tồn tại ⇒ không ai lấy lại được mã đã sinh ra số đó: **chặn** (mã thoát 1).
- `ok-da-biet` — `chet` **hoặc** `lech` nhưng nằm trong `CHO_PHEP` (có lý do ghi kèm). Nhãn in ra giữ
  trạng thái GỐC: `ok-da-biet(chet)` / `ok-da-biet(lech)` — hai chuyện khác nhau (rev mất hẳn ≠ rev còn
  sống mà không thuộc cây đang chạy), gộp làm một là mất thông tin.

**Cần lịch sử git đầy đủ**: trên clone `--depth 1` (shallow) mọi rev cũ đều "không tồn tại" ⇒ báo chết
oan. Job CI vì thế đặt `fetch-depth: 0`.

Cách dùng:
    python scripts/check_artifact_provenance.py            # quét `data/*_metrics.json`
    python scripts/check_artifact_provenance.py --nghiem   # CI: mã thoát 1 nếu có rev chết MỚI
    python scripts/check_artifact_provenance.py --nghiem --nghiem-lech   # chặt hơn: `lech` MỚI cũng chặn
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]

# Artifact có provenance KHÔNG TRUY ĐƯỢC nhưng giữ nguyên (không sửa tay bằng chứng đã commit) — khoá
# `(tên_file, git_rev)`, mỗi mục phải nêu LÝ DO. Áp cho cả `chet` (rev mất hẳn) và `lech` (rev còn ở object
# local nhưng không phải tổ tiên của `HEAD` — ca "nhánh rebase trước khi push"). Có danh sách này thì cổng
# vẫn bắt được rev chết/lệch MỚI (đúng lớp lỗi repo gặp 3 lần) mà CI không đỏ vì nợ lịch sử.
CHO_PHEP = {
    ("drift_2026-11-08_metrics.json", "ee9f256a1e77e6b4de08b0b0b8f4b0f0b8f0b0b8"):
        "field 40-hex KHÔNG tồn tại (nghi gõ tay 08-11), NHƯNG tiền tố `ee9f2567` trỏ tới commit THẬT "
        "`ee9f25672d72edfbb959726a7da396e01729de90` (commit sinh ra số) ⇒ dùng `ee9f25672d72`, đừng "
        "trích chuỗi 40 ký tự — xem `docs/task/08-11-2026-do-cai-gia-noi-suy-lk-va-nguong-nhieu.md`",
    # Hai artifact 10-11 đo từ relay webcam THẬT (không sinh lại được nếu không có camera đúng thời
    # điểm) nhưng rev chỉ tồn tại trong object LOCAL — nhánh bị rebase trước khi push, nên trên remote
    # `git cat-file -e` thất bại. Số trong `docs/doi-chieu-yeu-cau-gvhd.md` vẫn dùng được (đo thật),
    # chỉ là không truy được về commit ⇒ CẤM dẫn rev.
    ("empty_window_2026-11-10_metrics.json", "eb008e3d414d1c4406cc641a1c3a703303017243"):
        "rev chỉ có trong object local (nhánh rebase trước khi push) — số thật 10-11, CẤM dẫn rev",
    ("live_web_relay_2026-11-10_metrics.json", "da1d671c3c20be6f98ea4a3f4674714ff1fdae6c"):
        "rev chỉ có trong object local (nhánh rebase trước khi push) — số relay webcam thật 10-11, "
        "CẤM dẫn rev",
    # ── Nhóm 20–22/11: cùng bệnh "rev chỉ có ở object LOCAL" nhưng nặng hơn — 5 rev dưới **không tồn
    # tại trên remote** (nhánh bị rebase/squash trước khi push). Phát hiện 25-11: máy dev thấy chúng là
    # `lech` (rev còn sống, không phải tổ tiên) nên job CI xanh-ở-nhà/đỏ-trên-GitHub suốt 3 ngày; chỉ
    # `git clone file://…` (chỉ copy object REACHABLE) mới tái hiện đúng `chet`. Số vẫn dùng được (đo
    # thật, `git_dirty_code = false`) nhưng **CẤM trích rev** vì không ai kiểm lại được.
    # Cách tự kiểm khi nghi: `git clone --branch main file://$PWD /tmp/ci && (cd /tmp/ci &&
    # python scripts/check_artifact_provenance.py --nghiem)`.
    ("ab_image_size_b1b_2026-11-20_metrics.json",
     "6969fc40661ce42a6a9916d23d62b6640ae30f45"):
        "rev không tồn tại trên remote (nhánh rebase trước khi push) — A/B image_size trên `b1b` 20-11, "
        "CẤM dẫn rev",
    ("ab_max_mad_b1b_2026-11-20_metrics.json",
     "891f4f50c2a637820fc015876d640af1c8184ee8"):
        "rev không tồn tại trên remote (nhánh rebase trước khi push) — A/B max_mad trên `b1b` 20-11, "
        "CẤM dẫn rev",
    ("ab_vos_every_b1b_2026-11-20_metrics.json",
     "d893517ebb56c5e3b056467052396dd13e9207af"):
        "rev không tồn tại trên remote (nhánh rebase trước khi push) — A/B vos_every trên `b1b` 20-11, "
        "CẤM dẫn rev",
    ("gpu_sweep_binh2_2026-11-22_metrics.json",
     "316c6e8018b57f2bece05001a4e38de91d012f3a"):
        "rev không tồn tại trên remote (nhánh rebase trước khi push) — sweep GPU 22-11 (số 0,7644/0,8161 "
        "trong AGENTS §6 vẫn dùng được), CẤM dẫn rev",
    ("gpu_sweep_binh2_2026-11-22_lan192-320_metrics.json", "316c6e8"):
        "cùng lần sweep GPU 22-11 (rev ghi dạng NGẮN 7 ký tự) — CẤM dẫn rev",
    ("gpu_sweep_binh2_2026-11-22_lan512-1024_metrics.json", "316c6e8"):
        "cùng lần sweep GPU 22-11 (rev ghi dạng NGẮN 7 ký tự) — CẤM dẫn rev",
}


def _git(*args: str) -> tuple[int, str]:
    p = subprocess.run(["git", *args], cwd=_REPO_ROOT, capture_output=True, text=True)
    return p.returncode, (p.stdout or p.stderr).strip()


def phan_loai(rev: str | None) -> str:
    """`ok` / `lech` / `chet` — xem docstring đầu file."""
    # `git_rev = "--help"` từng được chấm `ok`: git hiểu `--help` ở tầng trên ⇒ rc 0 cho cả hai lệnh
    # (âm tính giả). Chỉ nhận hex ngắn/dài hợp lệ (P3 review 17-11).
    if not rev:
        # Artifact SCHEMA CŨ (trước luật provenance 08-11): không có field `git_rev` ⇒ đây KHÔNG phải
        # "rev chết" (rev từng tồn tại rồi mất) mà là "chưa từng khai". Tách nhãn để không gộp hai
        # chuyện khác nhau (bài học P2 18-11) và để allowlist được theo NHÓM mà cổng vẫn bắt file MỚI.
        return "thieu-rev"
    if not re.fullmatch(r"[0-9a-fA-F]{7,40}", rev):
        return "chet"
    rc, _ = _git("rev-parse", "--verify", "--end-of-options", f"{rev}^{{commit}}")
    if rc != 0:
        return "chet"
    rc, _ = _git("merge-base", "--is-ancestor", rev, "HEAD")
    return "ok" if rc == 0 else "lech"


# Artifact SINH TRƯỚC luật provenance (schema cũ, KHÔNG có field `git_rev`) — giữ nguyên bằng chứng đã
# commit, không sửa tay số, nhưng **CẤM trích rev** (không có rev). Liệt kê theo TÊN để cổng vẫn bắt
# được file MỚI thiếu `git_rev` (đúng lớp lỗi 22-11: thêm 2 test/artifact mà quên khai).
# Vì sao phải có danh sách này: `main` đỏ job "git_rev của artifact" từ 22-11 chỉ vì 9 file dưới ⇒ cổng
# mất tác dụng (đỏ mãi = không ai đọc).
CHO_PHEP_KHONG_REV = {
    "identity_latch_chi_phi_2026-11-21_metrics.json":
        "đo 21-11 (chi phí latch) — schema cũ, không khai `git_rev`; số đã dùng trong AGENTS §6 "
        "nhưng KHÔNG được trích rev",
    "jump_gate_replay_2026-11-21_metrics.json":
        "đo 21-11 (replay cổng nhảy) — schema cũ, không khai `git_rev`; cấm trích rev",
    "remote_trang_comparison_metrics.json":
        "so sánh remote trắng (trước 21-11) — schema cũ, không khai `git_rev`; cấm trích rev",
    **{f"sach_binh{k}_lan{i}_metrics.json":
       "đo 'sạch' binh1/binh2 (trước 21-11) — schema cũ, không khai `git_rev`; cấm trích rev"
       for k in (1, 2) for i in (1, 2, 3)},
}


def quet(thu_muc: Path, cho_phep=None) -> list[dict]:
    """Mỗi artifact `*_metrics.json` → `{file, git_rev, trang_thai, goc, ghi_chu}`.

    `trang_thai` ∈ `ok` / `lech` / `chet` / `ok-da-biet` (**`chet` HOẶC `lech`** nhưng nằm trong
    `CHO_PHEP` — "đã biết, có lý do"). `goc` giữ nhãn TRƯỚC khi hạ allowlist: "đã biết" vì rev **chết**
    khác với "đã biết" vì rev **còn sống nhưng không phải tổ tiên** — gộp hai thứ đó thành một nhãn
    "chết-đã-biết" làm mất thông tin (P2 review 18-11).
    """
    cho_phep = CHO_PHEP if cho_phep is None else cho_phep
    ra = []
    for f in sorted(thu_muc.glob("*_metrics.json")):
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            # `goc` cho ĐỒNG SCHEMA: mọi record đều có, nơi đọc không phải `KeyError`-theo-nhánh.
            ra.append({"file": f.name, "git_rev": None, "trang_thai": "chet", "goc": "chet",
                       "ghi_chu": "artifact không đọc được"})
            continue
        rev = d.get("git_rev") if isinstance(d, dict) else None
        trang_thai = phan_loai(rev)
        ghi_chu = None
        # `lech` CŨNG phải hạ được: hai artifact 10-11 có rev chỉ tồn tại ở object local (nhánh bị
        # rebase trước khi push) ⇒ chúng `lech` vĩnh viễn trên máy này, và dòng "2 lệch" cố định sẽ
        # **che mất một `lech` MỚI** (cổng phải kêu khi có chuyện mới, không kêu mãi một chuyện cũ).
        goc = trang_thai                               # nhãn GỐC — không được mất khi hạ allowlist
        if trang_thai == "thieu-rev" and f.name in CHO_PHEP_KHONG_REV:
            trang_thai, ghi_chu = "ok-da-biet", CHO_PHEP_KHONG_REV[f.name]
        if trang_thai in ("chet", "lech") and (f.name, rev) in cho_phep:
            trang_thai, ghi_chu = "ok-da-biet", cho_phep[(f.name, rev)]
        ra.append({"file": f.name, "git_rev": rev, "trang_thai": trang_thai, "goc": goc,
                   "ghi_chu": ghi_chu})
    return ra


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Kiểm git_rev trong data/*_metrics.json.")
    ap.add_argument("--thu-muc", default=None, help="thư mục artifact (mặc định `data/`)")
    ap.add_argument("--nghiem", action="store_true",
                    help="thoát 1 nếu có `git_rev` chết MỚI (rev trong `CHO_PHEP` không tính)")
    ap.add_argument("--nghiem-lech", action="store_true",
                    help="thoát 1 cả khi có `lech` MỚI (rev còn sống nhưng KHÔNG phải tổ tiên của HEAD). "
                         "Mặc định TẮT vì `lech` là trạng thái hợp lệ của nhánh chưa merge; bật khi muốn "
                         "cổng chặt cho artifact đã commit vào `main`")
    args = ap.parse_args(argv)
    thu_muc = Path(args.thu_muc) if args.thu_muc else (_REPO_ROOT / "data")
    if not thu_muc.is_dir():
        print(f"[provenance] không có thư mục {thu_muc}")
        return 2

    ket_qua = quet(thu_muc)
    if not ket_qua:
        # `0 artifact` KHÔNG phải "đã kiểm" (AGENTS §6). Glob ngừng khớp (đổi tên artifact) hoặc `data/`
        # rỗng mà job vẫn xanh là đúng bẫy `0/None ≠ đã đo`.
        print(f"[provenance] {thu_muc} không có artifact nào — không phải 'đã kiểm' (AGENTS §6)")
        return 2

    chet = [r for r in ket_qua if r["trang_thai"] == "chet"]
    lech = [r for r in ket_qua if r["trang_thai"] == "lech"]
    da_biet = [r for r in ket_qua if r["trang_thai"] == "ok-da-biet"]
    for r in ket_qua:
        if r["trang_thai"] == "ok":
            continue                                   # im lặng cho 44 artifact bình thường
        rev = (r["git_rev"] or "")[:7] or "—"
        nhan = (f"{r['trang_thai']}({r['goc']})" if r["trang_thai"] == "ok-da-biet"
                else r["trang_thai"])
        print(f"{nhan:18} {r['file']:52} {rev}")
        if r["ghi_chu"]:
            print(f"            └ {r['ghi_chu']}")
    print(f"\n[provenance] {len(ket_qua)} artifact: "
          f"{len(ket_qua) - len(chet) - len(lech) - len(da_biet)} ok · {len(lech)} lệch · "
          f"{len(da_biet)} đã-biết · {len(chet)} CHẾT-MỚI")
    ten_file = {r["file"] for r in ket_qua}
    treo = [k for k in CHO_PHEP if k[0] not in ten_file]
    for ten, _rev in treo:
        print(f"[provenance] CẢNH BÁO: allowlist còn mục `{ten}` nhưng không có artifact đó — gỡ khỏi "
              "`CHO_PHEP` nếu artifact đã bị xoá/đổi tên", file=sys.stderr)
    if chet and not args.nghiem:
        print("[provenance] cảnh báo: có rev chết mới (dùng --nghiem để chặn)", file=sys.stderr)
    if lech:
        print(f"[provenance] {len(lech)} rev `lech` — còn sống nhưng KHÔNG thuộc cây đang chạy "
              "(artifact cũ/khác nhánh). Mặc định chỉ cảnh báo; `--nghiem-lech` để chặn.",
              file=sys.stderr)
    # GOM mã thoát: bản trước `return` sớm ở nhánh `chet` nên `--nghiem-lech` bị NUỐT khi có `chet` mà
    # không có `--nghiem` (gọi script trực tiếp, không qua `./run provcheck` luôn chèn `--nghiem`).
    if chet:
        print("[provenance] CHẾT = `git_rev` không tồn tại (thường do rebase/squash hoặc artifact bị "
              "sinh lại đè): số đo không tái lập được ⇒ ghi rõ trong tài liệu hoặc sinh lại artifact "
              "trên cây sạch", file=sys.stderr)
    if lech and args.nghiem_lech:
        print(f"[provenance] --nghiem-lech: {len(lech)} rev `lech` ⇒ thoát 1", file=sys.stderr)
    return 1 if (chet and args.nghiem) or (lech and args.nghiem_lech) else 0


if __name__ == "__main__":
    sys.exit(main())
