"""
Định mức nhiễu (noise floor) cho các phép so sánh A/B trong repo.

Chức năng: chạy lại CÙNG một lệnh nhiều lần rồi tính độ tản của các chỉ số; độ tản đó là **ngưỡng
           nhỏ nhất** để một khác biệt giữa hai cấu hình được coi là thật.
Input  : danh sách giá trị đo (mỗi lần chạy một giá trị) hoặc danh sách dict nhiều chỉ số.
Output : dict {mean, min, max, rel_spread, spread} + hàm `la_khac_biet()` để kết luận A/B.
Lưu ý  : SAM 2 **không tất định** (cùng seed/video, hai lần chạy cho ô bao cuối khác nhau — đo
         08-11). Vì vậy mọi câu "A tốt hơn B" phải kèm ngưỡng nhiễu này; nhỏ hơn ⇒ "inconclusive".
         Hàm thuần, không import torch ⇒ test headless được.
"""

import statistics


def spread(values) -> dict:
    """Độ tản của một chỉ số qua nhiều lần chạy CÙNG cấu hình."""
    data = [float(v) for v in values]
    if not data:
        raise ValueError("cần ít nhất 1 giá trị")
    mean = statistics.fmean(data)
    low, high = min(data), max(data)
    return {
        "n": len(data),
        "mean": round(mean, 4),
        "min": round(low, 4),
        "max": round(high, 4),
        "spread": round(high - low, 4),
        # độ tản tương đối: dùng để so các chỉ số khác đơn vị (ms vs FPS vs IoU)
        "rel_spread": round((high - low) / mean, 4) if mean else 0.0,
    }


def la_khac_biet(a: float, b: float, nguong: float, n: int | None = None) -> bool:
    """Hai số khác nhau **thật** hay chỉ là nhiễu? `nguong` lấy từ `spread(...)["spread"]`.

    `n < 2` ⇒ CHƯA có ngưỡng nhiễu (1 lần chạy không cho độ tản) ⇒ luôn trả False: thà nói
    "không phân biệt được" còn hơn kết luận "khác thật" từ một phép đo duy nhất.
    """
    if n is not None and n < 2:
        return False
    return abs(float(a) - float(b)) > float(nguong)


def danh_gia(ket_qua: dict) -> str:
    """Câu kết luận trung thực cho một phép A/B.

    ket_qua = {"a": tên, "b": tên, "a_mean": x, "b_mean": y, "nguong": s}
    """
    a, b = ket_qua["a"], ket_qua["b"]
    if la_khac_biet(ket_qua["a_mean"], ket_qua["b_mean"], ket_qua["nguong"]):
        return (f"{a} ({ket_qua['a_mean']}) khác {b} ({ket_qua['b_mean']}) vượt ngưỡng nhiễu "
                f"{ket_qua['nguong']}")
    n = ket_qua.get("n")
    duoi = f" (ngưỡng nhiễu {ket_qua['nguong']}, n={n})" if n else f" (ngưỡng nhiễu {ket_qua['nguong']})"
    return (f"KHÔNG PHÂN BIỆT ĐƯỢC {a} ({ket_qua['a_mean']}) và {b} ({ket_qua['b_mean']}): chênh "
            f"lệch không vượt ngưỡng nhiễu{duoi} ⇒ inconclusive")
