

class TestTimWorkerMoCoi:
    """21-11 (bug thật): worker của phiên WEB bị bỏ quên ăn 461 % CPU ⇒ `./run demoip` đo được

    1484 ms/frame thay vì 158 ms, không một dòng cảnh báo — cả buổi demo bị kết luận sai là
    "model chậm". `find_live_workers` là thứ cho CLI biết để in cảnh báo kèm pid.
    """

    def _gia_lap(self, tmp_path):
        """/proc giả: vài tiến trình, trong đó 2 là worker live."""
        root = tmp_path / "proc"
        for pid, argv in (
            (101, ["python", "tools/live_worker.py", "--out-dir", "/dev/shm/doan-live"]),
            (102, ["python", "tools/live_worker.py", "--out-dir", "/tmp/khac"]),
            (103, ["python", "tools/run_live.py", "--source", "0"]),
            (104, []),
        ):
            d = root / str(pid)
            d.mkdir(parents=True)
            (d / "cmdline").write_bytes("\0".join(argv).encode() + b"\0")
        (root / "self").mkdir()          # mục không phải pid ⇒ bỏ qua
        return root

    def test_tim_duoc_worker_va_khong_lan_sang_tien_trinh_khac(self, tmp_path):
        from src.proc_pid import find_live_workers

        root = self._gia_lap(tmp_path)
        found = find_live_workers(proc_root=str(root))
        assert sorted(pid for pid, _ in found) == [101, 102], found

    def test_exclude_pid_bo_qua_chinh_minh(self, tmp_path):
        from src.proc_pid import find_live_workers

        root = self._gia_lap(tmp_path)
        found = find_live_workers(proc_root=str(root), exclude_pid=101)
        assert [pid for pid, _ in found] == [102]

    def test_proc_khong_ton_tai_thi_tra_rong_khong_nem(self, tmp_path):
        from src.proc_pid import find_live_workers

        assert find_live_workers(proc_root=str(tmp_path / "khong-co")) == []
