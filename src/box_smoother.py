"""Làm mượt **ô bao được VẼ RA** trên đường CLI (`--smooth`) — không đụng tới kết quả model.

Vì sao cần (đo 25-11, phiên `data/demoip_1125-100334`): đường `./run demoip` KHÔNG có LK (khác
đường web), nên giữa hai bước VOS ô **đứng yên** rồi **nhảy**. Đo trực tiếp trên video HUD (ô đỏ
dò theo màu, 241 frame hiển thị trong 18–26 s):

    chuỗi đứng yên  : med **9 frame hiển thị** (~300 ms) rồi nhảy
    bước nhảy tâm   : med **22,7 px**, max **118 px**
    bước nhảy bề rộng: med 7 px, max 28 px

Người dùng gọi hiện tượng đó là *"box đỏ hơi dựt lag"*. Mô phỏng lại CHÍNH dãy ô đã ghi, làm mượt
bằng EMA theo **frame hiển thị** (τ ≈ 125 ms):

    hiện tại        : dịch chuyển/frame med 0,00 px · p95 22,7 · **max 118,1**
    EMA τ=125 ms    : dịch chuyển/frame med 1,35 px · p95 22,2 · **max  41,8**
    trễ ổn định     : **~0 frame** (tương quan chéo cực đại ở lag 0; sai khác trung bình 4,6 px)
    ⇒ mượt mà KHÔNG thêm trễ thường trực: mỗi cú nhảy được "tráng" qua ~5–8 frame hiển thị, và vì
      khoảng giữa hai bước VOS cũng ~9 frame nên ô vẫn bám kịp trước lần cập nhật kế.

Nguyên tắc an toàn (giữ đúng luật repo — số hiệu năng/độ trễ phải trung thực):
- **Chỉ làm mượt ô VẼ RA.** `result.bbox` (dùng cho cổng nghi, metrics, quỹ đạo, mIoU) KHÔNG đổi.
- **Cú nhảy lớn thì SNAP, không tráng**: nếu tâm lệch quá `snap_ratio × đường chéo` thì lấy ngay ô
  mới. Tráng một cú nhảy 200 px sẽ thành một vệt quét ngang khung — đúng thứ trông như "bám bừa".
- Ô rỗng `(0,0,0,0)` ⇒ `reset()`: khi vật hiện lại, ô phải xuất hiện đúng chỗ, không bò từ chỗ cũ.
- Hàm thuần, không I/O, test được không cần model/khung hình thật.

Cắm vào đâu: `src/smooth_display.run_smooth_display(box_smooth_tau_ms=...)` — mặc định **0 (TẮT)**
để artifact cũ tái lập được; `./run demoip` bật 125 ms.
"""
from __future__ import annotations

import math

# Hằng số đo được (25-11) — đổi phải đo lại rồi cập nhật số trong docstring module này.
DEFAULT_TAU_MS = 125.0
DEFAULT_SNAP_RATIO = 0.25      # cùng thang với `identity_guard.DEFAULT_MAX_JUMP_RATIO`


def _center(bbox):
    return (bbox[0] + bbox[2]) / 2.0, (bbox[1] + bbox[3]) / 2.0


def _rong(bbox) -> bool:
    x1, y1, x2, y2 = (float(v) for v in bbox)
    return x2 > x1 and y2 > y1


class BoxSmoother:
    """EMA trên 4 toạ độ ô, hệ số suy ra từ **thời gian** (không phụ thuộc FPS hiển thị).

    `tau_ms` = hằng số thời gian: sau `tau_ms` ô đi được ~63 % quãng đường tới ô mới. 125 ms là số
    đo được trên phiên 25-11 (mục "vì sao cần" ở docstring module).

    `dt` mặc định: nếu người gọi không truyền `dt_s`, dùng `1/30 s` (nhịp vẽ của `smooth_display`
    trước 24-11). Truyền `dt_s` thật khi có (nhịp vẽ thật ~18–20 tick/s) để tốc độ mượt không đổi
    theo máy.
    """

    def __init__(self, tau_ms: float = DEFAULT_TAU_MS,
                 snap_ratio: float = DEFAULT_SNAP_RATIO, dt_mac_dinh_s: float = 1 / 30):
        self.tau_ms = max(1e-3, float(tau_ms))
        self.snap_ratio = max(0.0, float(snap_ratio))
        self.dt_mac_dinh_s = max(1e-3, float(dt_mac_dinh_s))
        self._o = None             # ô đang vẽ (float, 4 phần tử) — None = chưa có gì để mượt
        self._snap = 0             # số lần SNAP (chẩn đoán: nhiều snap = có gì đó nhảy liên tục)
        self._so_buoc = 0

    @property
    def o_dang_ve(self):
        """Ô đang vẽ (tuple int) hoặc `None` — đọc được để test/telemetry."""
        return None if self._o is None else tuple(int(round(v)) for v in self._o)

    @property
    def so_lan_snap(self) -> int:
        return self._snap

    @property
    def so_buoc(self) -> int:
        return self._so_buoc

    def reset(self) -> None:
        self._o = None

    def _alpha(self, dt_s) -> float:
        dt = self.dt_mac_dinh_s if dt_s is None else max(0.0, float(dt_s))
        return 1.0 - math.exp(-dt * 1000.0 / self.tau_ms)

    def update(self, bbox, frame_shape=None, dt_s=None):
        """Nạp ô model vừa trả về, trả **ô nên vẽ** (tuple int 4 phần tử).

        `bbox` rỗng `(0,0,0,0)` (mất dấu) ⇒ xoá trạng thái và trả nguyên `(0,0,0,0)`.
        `frame_shape` = (H, W) để tính ngưỡng SNAP; thiếu thì ngưỡng SNAP **tắt** (không đoán bừa) —
        nhưng vẫn EMA, nên người gọi nên truyền vào.
        """
        if bbox is None or len(tuple(bbox)) != 4 or not _rong(bbox):
            self.reset()
            return (0, 0, 0, 0)
        moi = tuple(float(v) for v in bbox)
        self._so_buoc += 1
        if self._o is None:
            self._o = moi
            return tuple(int(round(v)) for v in moi)

        # SNAP: cú nhảy lớn KHÔNG được tráng (xem docstring module).
        if frame_shape is not None and self.snap_ratio > 0:
            h, w = float(frame_shape[0]), float(frame_shape[1])
            tran = self.snap_ratio * math.hypot(w, h)
            cx_cu, cy_cu = _center(self._o)
            cx_moi, cy_moi = _center(moi)
            if math.hypot(cx_moi - cx_cu, cy_moi - cy_cu) > tran:
                self._snap += 1
                self._o = moi
                return tuple(int(round(v)) for v in moi)

        a = self._alpha(dt_s)
        self._o = tuple(a * m + (1.0 - a) * c for c, m in zip(self._o, moi))
        # Bảo vệ: cận trên/dưới không được đảo (EMA trên 4 toạ độ độc lập có thể đảo nếu ô co cực
        # nhanh — khi đó vẽ hình chữ nhật ngược sẽ ra đường kẻ lạ).
        x1, y1, x2, y2 = self._o
        if x2 <= x1:
            x2 = x1 + 1.0
        if y2 <= y1:
            y2 = y1 + 1.0
        self._o = (x1, y1, x2, y2)
        return tuple(int(round(v)) for v in self._o)
