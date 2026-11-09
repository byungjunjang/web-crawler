"""#1에서 분리한 CA 경로 및 preflight 회귀 검사. 외부 요청은 하지 않는다."""
import importlib.util
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

import utils


@pytest.fixture
def ca_paths(monkeypatch, tmp_path):
    if not str(tmp_path).isascii():
        pytest.skip("ASCII 캐시 경로를 검증하는 테스트")
    for key in ("CURL_CA_BUNDLE", "REQUESTS_CA_BUNDLE", "SSL_CERT_FILE"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setattr(utils, "_IS_WINDOWS", True)
    src = tmp_path / "인증서" / "cacert.pem"
    src.parent.mkdir()
    src.write_bytes(b"AAAA")
    cache = tmp_path / "cache"
    monkeypatch.setattr("certifi.where", lambda: str(src))
    monkeypatch.setattr(utils, "_ca_cache_candidates", lambda: [str(cache)])
    return src, cache


def test_same_size_ca_update_refreshes_cache(ca_paths, monkeypatch):
    src, _ = ca_paths
    dest = Path(utils.ensure_ascii_ca_bundle())
    assert dest.read_bytes() == b"AAAA"
    src.write_bytes(b"BBBB")
    monkeypatch.delenv("CURL_CA_BUNDLE")
    assert utils.ensure_ascii_ca_bundle() == str(dest)
    assert dest.read_bytes() == b"BBBB"


def test_failed_replace_keeps_previous_ca(ca_paths, monkeypatch):
    src, cache = ca_paths
    dest = Path(utils.ensure_ascii_ca_bundle())
    src.write_bytes(b"BBBB")
    monkeypatch.delenv("CURL_CA_BUNDLE")
    def fail(*args):
        raise OSError("replace failed")
    monkeypatch.setattr(utils.os, "replace", fail)
    assert utils.ensure_ascii_ca_bundle() is None
    assert dest.read_bytes() == b"AAAA"
    assert list((cache / "web-crawler").iterdir()) == [dest]


@pytest.mark.parametrize("key", ["CURL_CA_BUNDLE", "REQUESTS_CA_BUNDLE", "SSL_CERT_FILE"])
def test_user_ca_override_is_preserved(ca_paths, monkeypatch, key):
    _, cache = ca_paths
    monkeypatch.setenv(key, "custom.pem")
    assert utils.ensure_ascii_ca_bundle() is None
    assert os.environ[key] == "custom.pem"
    assert not cache.exists()


def test_non_windows_does_not_create_cache(ca_paths, monkeypatch):
    _, cache = ca_paths
    monkeypatch.setattr(utils, "_IS_WINDOWS", False)
    assert utils.ensure_ascii_ca_bundle() is None
    assert not cache.exists()


def test_ascii_source_does_not_create_cache(ca_paths, monkeypatch, tmp_path):
    _, cache = ca_paths
    monkeypatch.setattr("certifi.where", lambda: str(tmp_path / "cacert.pem"))
    assert utils.ensure_ascii_ca_bundle() is None
    assert not cache.exists()


def test_import_has_no_ca_side_effect(ca_paths):
    _, cache = ca_paths
    spec = importlib.util.spec_from_file_location("utils_import_test", utils.__file__)
    spec.loader.exec_module(importlib.util.module_from_spec(spec))
    assert "CURL_CA_BUNDLE" not in os.environ
    assert not cache.exists()


@pytest.mark.parametrize("mode", ["get", "session"])
def test_http_entry_points_prepare_ca(ca_paths, monkeypatch, mode):
    import scrapling.fetchers
    _, cache = ca_paths
    def check(*args, **kwargs):
        assert Path(os.environ["CURL_CA_BUNDLE"]).read_bytes() == b"AAAA"
        return "response"
    if mode == "get":
        monkeypatch.setattr(scrapling.fetchers.Fetcher, "get", check)
        assert utils.plain_get("https://example.com") == "response"
    else:
        monkeypatch.setattr(scrapling.fetchers, "FetcherSession", check)
        assert utils.plain_session() == "response"


@pytest.mark.parametrize("code,expected", [(77, "FAIL"), (7, "WARN")])
def test_preflight_distinguishes_ca_and_network_errors(monkeypatch, code, expected):
    from curl_cffi import CurlError
    import preflight
    def fail(*args, **kwargs):
        raise CurlError("fetch failed", code=code)
    recorded = []
    monkeypatch.setattr(utils, "plain_get", fail)
    monkeypatch.setattr(preflight, "record", lambda *args: recorded.append(args))
    assert preflight.check_http_fetch() is (expected != "FAIL")
    assert recorded[0][1] == expected


def test_preflight_success(monkeypatch):
    import preflight
    recorded = []
    monkeypatch.setattr(utils, "plain_get", lambda *a, **kw: SimpleNamespace(status=200))
    monkeypatch.setattr(preflight, "record", lambda *args: recorded.append(args))
    assert preflight.check_http_fetch() is True
    assert recorded[0][1] == "PASS"
