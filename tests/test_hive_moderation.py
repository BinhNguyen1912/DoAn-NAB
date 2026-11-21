"""Test client Hive AI — mock urllib, KHÔNG gọi API thật, KHÔNG cần key."""

import io
import json
import urllib.error

import pytest

import src.hive_moderation as hm


def test_thieu_key_bao_loi_ro_rao(monkeypatch, tmp_path):
    monkeypatch.delenv(hm.API_KEY_ENV, raising=False)
    monkeypatch.setattr(hm, "_ENV_PATH", tmp_path / "khong-co.env")

    with pytest.raises(hm.HiveError, match="thiếu HIVE_API_KEY"):
        hm.submit_sync({"url": "x", "tasks": []})


def test_load_dotenv_khi_bien_moi_truong_chua_co(monkeypatch, tmp_path):
    env = tmp_path / ".env"
    env.write_text("HIVE_API_KEY=abc123\n# ghi chu\nOTHER=khong-lien-quan\n", encoding="utf-8")
    monkeypatch.setattr(hm, "_ENV_PATH", env)
    monkeypatch.delenv(hm.API_KEY_ENV, raising=False)

    assert hm._api_key() == "abc123"


def test_bien_moi_truong_thang_dotenv(monkeypatch, tmp_path):
    env = tmp_path / ".env"
    env.write_text("HIVE_API_KEY=tu-dotenv\n", encoding="utf-8")
    monkeypatch.setattr(hm, "_ENV_PATH", env)
    monkeypatch.setenv(hm.API_KEY_ENV, "tu-moi-truong")

    assert hm._api_key() == "tu-moi-truong"


def test_goi_dung_header_va_body(monkeypatch):
    captured = {}

    class _Resp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return b'{"status": {"success": true}}'

    def _fake_urlopen(request, timeout=30):
        captured["request"] = request
        captured["timeout"] = timeout
        return _Resp()

    monkeypatch.setattr(hm.urllib.request, "urlopen", _fake_urlopen)

    result = hm.submit_sync({"url": "https://x/y.jpg", "tasks": [{"type": "moderation"}]},
                            api_key="k123")

    request = captured["request"]
    assert request.full_url == hm.SYNC_URL
    assert request.get_header("Authorization") == "token k123"
    assert request.get_header("Content-type") == "application/json"
    assert json.loads(request.data.decode("utf-8"))["tasks"] == [{"type": "moderation"}]
    assert result == {"status": {"success": True}}


def test_http_400_bao_loi_kem_noi_dung(monkeypatch):
    def _fake_urlopen(request, timeout=30):
        body = b'{"return_code": 400, "message": "Invalid Auth Method"}'
        raise urllib.error.HTTPError(request.full_url, 400, "Bad", {}, io.BytesIO(body))

    monkeypatch.setattr(hm.urllib.request, "urlopen", _fake_urlopen)

    with pytest.raises(hm.HiveError, match="Invalid Auth Method"):
        hm.submit_sync({}, api_key="k")


def test_mang_chet_bao_loi(monkeypatch):
    def _fake_urlopen(request, timeout=30):
        raise urllib.error.URLError("timeout")

    monkeypatch.setattr(hm.urllib.request, "urlopen", _fake_urlopen)

    with pytest.raises(hm.HiveError, match="không tới được"):
        hm.submit_sync({}, api_key="k")
