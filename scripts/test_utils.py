"""scripts/test_utils.py"""
import json
import os
import shutil
import tempfile
import time
from pathlib import Path

import pytest
from unittest.mock import patch
from utils import (
    RateLimiter,
    ensure_ascii_ca_bundle,
    detect_pii,
    load_cookies,
    save_cookies,
    load_auth_token,
    save_auth_token,
    setup_logger,
    validate_url,
    sanitize_filename,
)


def test_rate_limiter_enforces_delay():
    # delay 하한(0.5) 이 있으므로 그 이상 값으로 검증한다 — P2-3
    limiter = RateLimiter(delay=0.5)
    start = time.time()
    limiter.wait()
    limiter.wait()
    elapsed = time.time() - start
    assert elapsed >= 0.5


def test_rate_limiter_backoff_on_429():
    # delay 하한(0.5) 이하 값은 하한으로 올라가므로 하한 이상 값으로 검증한다 — P2-3
    limiter = RateLimiter(delay=0.5)
    limiter.backoff()
    assert limiter.delay == 1.0  # doubled


def test_validate_url_valid():
    assert validate_url("https://example.com/products") is True
    assert validate_url("http://example.com") is True


def test_validate_url_invalid():
    assert validate_url("not-a-url") is False
    assert validate_url("") is False
    assert validate_url("ftp://example.com") is False


def test_sanitize_filename():
    assert sanitize_filename("example.com") == "example_com"
    assert sanitize_filename("a/b:c*d") == "a_b_c_d"


def test_save_and_load_cookies(tmp_path):
    cookies = {"session": "abc123", "token": "xyz"}
    filepath = tmp_path / "cookies.json"
    save_cookies(cookies, str(filepath))
    loaded = load_cookies(str(filepath))
    assert loaded == cookies


def test_load_cookies_expired(tmp_path):
    cookies = {"session": "abc123"}
    filepath = tmp_path / "cookies.json"
    save_cookies(cookies, str(filepath))
    # Simulate 25 hours old
    old_time = time.time() - (25 * 3600)
    os.utime(str(filepath), (old_time, old_time))
    loaded = load_cookies(str(filepath))
    assert loaded is None  # expired (24h policy)


def test_save_and_load_auth_token(tmp_path):
    token = "eyJhbGciOiJIUzI1NiJ9.test_payload.signature"
    filepath = tmp_path / "token.json"
    save_auth_token(token, str(filepath), token_type="bearer")
    loaded = load_auth_token(str(filepath))
    assert loaded == {"type": "bearer", "token": token}


def test_load_auth_token_expired(tmp_path):
    filepath = tmp_path / "token.json"
    save_auth_token("expired_token", str(filepath))
    old_time = time.time() - (25 * 3600)
    os.utime(str(filepath), (old_time, old_time))
    loaded = load_auth_token(str(filepath))
    assert loaded is None


def test_setup_logger():
    logger = setup_logger("test_crawler")
    assert logger.name == "test_crawler"


def test_detect_pii_email():
    from utils import detect_pii
    data = [{"name": "홍길동", "contact": "hong@email.com"}]
    warnings = detect_pii(data)
    assert len(warnings) > 0
    assert "이메일" in warnings[0]


def test_detect_pii_phone():
    from utils import detect_pii
    data = [{"name": "홍길동", "phone": "010-1234-5678"}]
    warnings = detect_pii(data)
    assert len(warnings) > 0


def test_detect_pii_clean():
    from utils import detect_pii
    data = [{"name": "상품A", "price": "10000"}]
    warnings = detect_pii(data)
    assert len(warnings) == 0


# ── S1: 사다리 1·2단 위장 끄기 ──

from utils import PLAIN_KWARGS, plain_get, plain_session


def test_plain_kwargs_has_both_arguments():
    """부분 적용은 악화다 — 두 인자가 항상 함께 있어야 한다."""
    assert PLAIN_KWARGS == {"impersonate": None, "stealthy_headers": False}


def test_plain_get_passes_both_arguments(monkeypatch):
    captured = {}

    class _FakeFetcher:
        @staticmethod
        def get(url, **kw):
            captured["url"] = url
            captured["kw"] = kw
            return "response"

    monkeypatch.setattr("scrapling.fetchers.Fetcher", _FakeFetcher)

    assert plain_get("https://example.com") == "response"
    assert captured["url"] == "https://example.com"
    assert captured["kw"]["impersonate"] is None
    assert captured["kw"]["stealthy_headers"] is False


def test_plain_get_allows_explicit_override(monkeypatch):
    """호출자가 명시적으로 덮을 수는 있다 — 단 둘을 함께 덮어야 한다."""
    captured = {}

    class _FakeFetcher:
        @staticmethod
        def get(url, **kw):
            captured.update(kw)
            return "response"

    monkeypatch.setattr("scrapling.fetchers.Fetcher", _FakeFetcher)

    plain_get("https://example.com", impersonate="chrome", stealthy_headers=True)
    assert captured["impersonate"] == "chrome"
    assert captured["stealthy_headers"] is True


def test_plain_session_passes_both_arguments(monkeypatch):
    captured = {}

    class _FakeSession:
        def __init__(self, **kw):
            captured.update(kw)

    monkeypatch.setattr("scrapling.fetchers.FetcherSession", _FakeSession)

    plain_session()
    assert captured["impersonate"] is None
    assert captured["stealthy_headers"] is False


def test_plain_helpers_do_not_import_scrapling_at_module_level():
    """utils 는 scrapling 을 물지 않는다 — import 는 함수 안에서 lazy 하게.

    AST 의 최상위 노드만 본다. 문자열 검색은 두 방향으로 틀린다 —
    파일 뒤쪽에 덧붙은 코드를 놓치고, 메서드 안의 정당한 lazy import 를 오탐한다.
    """
    import ast
    from pathlib import Path

    import utils

    tree = ast.parse(Path(utils.__file__).read_text(encoding="utf-8"))
    for node in tree.body:              # 최상위만 — 함수/클래스 내부는 보지 않는다
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            names = [node.module or ""]
        else:
            continue
        offenders = [n for n in names if n.startswith("scrapling")]
        assert not offenders, f"utils 모듈 최상단에서 scrapling 을 import 하고 있습니다: {offenders}"


def test_plain_get_rejects_partial_override():
    """한쪽만 끄거나 켜는 것은 악화다 — 조용히 허용하지 않는다."""
    with pytest.raises(ValueError, match="impersonate"):
        plain_get("https://example.com", stealthy_headers=True)
    with pytest.raises(ValueError, match="stealthy_headers"):
        plain_get("https://example.com", impersonate="chrome")


def test_plain_session_rejects_partial_override():
    with pytest.raises(ValueError, match="stealthy_headers"):
        plain_session(impersonate="chrome")


# ── P2-1: robots.txt ──
from utils import check_robots


def _fake_fetch(body, status=200):
    def _fetch(url, timeout=10):
        return body, status
    return _fetch


def test_robots_allows_when_not_disallowed(monkeypatch):
    monkeypatch.setattr("utils._fetch_robots", _fake_fetch("User-agent: *\nAllow: /"))
    result = check_robots("https://example.com/list")
    assert result["allowed"] is True
    assert result["robots_url"] == "https://example.com/robots.txt"


def test_robots_blocks_disallowed_path(monkeypatch):
    monkeypatch.setattr("utils._fetch_robots",
                        _fake_fetch("User-agent: *\nDisallow: /private"))
    assert check_robots("https://example.com/private/x")["allowed"] is False
    assert check_robots("https://example.com/public/x")["allowed"] is True


def test_robots_blocks_everything(monkeypatch):
    monkeypatch.setattr("utils._fetch_robots", _fake_fetch("User-agent: *\nDisallow: /"))
    assert check_robots("https://example.com/anything")["allowed"] is False


def test_robots_reports_crawl_delay(monkeypatch):
    monkeypatch.setattr("utils._fetch_robots",
                        _fake_fetch("User-agent: *\nCrawl-delay: 5"))
    assert check_robots("https://example.com/")["crawl_delay"] == 5.0


def test_robots_missing_file_allows(monkeypatch):
    """robots.txt 가 404 면 제한이 없는 것으로 본다 (표준 동작)."""
    monkeypatch.setattr("utils._fetch_robots", _fake_fetch("", 404))
    assert check_robots("https://example.com/")["allowed"] is True


def test_robots_network_error_is_reported_not_swallowed(monkeypatch):
    """가져오지 못한 것과 허용된 것은 다르다 — 사용자가 구분할 수 있어야 한다."""
    def _boom(url, timeout=10):
        raise OSError("connection refused")
    monkeypatch.setattr("utils._fetch_robots", _boom)
    result = check_robots("https://example.com/")
    assert result["error"] is not None
    assert result["allowed"] is True     # 차단 근거가 없으므로 막지는 않는다


# ── P2-2: PII 스키마 감지 ──
def test_pii_detects_author_column_names():
    warnings = detect_pii([{"작성자": "홍길동", "평점": 5}])
    assert any("작성자" in w for w in warnings)


def test_pii_detects_english_author_columns():
    for column in ("author", "writer", "nickname", "user_name", "reviewer"):
        warnings = detect_pii([{column: "someone"}])
        assert warnings, f"컬럼명 '{column}' 을 감지하지 못했습니다"


def test_pii_detects_korean_identity_columns():
    for column in ("이름", "닉네임", "아이디", "회원명"):
        warnings = detect_pii([{column: "값"}])
        assert warnings, f"컬럼명 '{column}' 을 감지하지 못했습니다"


def test_pii_schema_warning_reported_once_per_column():
    """행마다 반복하지 않는다 — 스키마는 데이터셋당 한 번이다."""
    data = [{"작성자": f"user{i}"} for i in range(30)]
    author_warnings = [w for w in detect_pii(data) if "작성자" in w]
    assert len(author_warnings) == 1


def test_pii_ignores_innocent_columns():
    assert detect_pii([{"상품명": "사과", "가격": 1000}]) == []


def test_pii_still_detects_values():
    """기존 값 기반 감지는 그대로 동작한다."""
    assert detect_pii([{"메모": "문의는 a@b.com 으로"}])


# ── P2-2 픽스: 집계·파생 컬럼 오탐 제거 ──
@pytest.mark.parametrize("column", [
    "작성자", "이름", "닉네임", "아이디", "회원명", "구매자",
    "author", "writer", "nickname", "user_name", "reviewer", "member",
])
def test_pii_still_flags_genuine_identity_columns(column):
    """집계 접미사 제외 로직을 넣은 뒤에도 진짜 개인 컬럼은 그대로 잡혀야 한다 — 회귀 방지."""
    warnings = detect_pii([{column: "값"}])
    assert warnings, f"컬럼명 '{column}' 을 감지하지 못했습니다"


@pytest.mark.parametrize("column", [
    "회원수", "구매자수", "작성자수",
    "buyer_count", "author_count", "member_count",
    "customer_satisfaction_score", "profile_view_count", "username_policy",
])
def test_pii_ignores_aggregate_columns(column):
    """어근이 같아도 집계·파생 컬럼은 사람이 아니라 사람에 대한 수치다."""
    warnings = detect_pii([{column: "x"}])
    assert warnings == [], f"집계 컬럼 '{column}' 이 잘못 감지되었습니다: {warnings}"


@pytest.mark.parametrize("column", [
    "상품명", "가격", "제목", "내용", "카테고리", "브랜드", "평점", "등록일",
])
def test_pii_still_ignores_unrelated_columns(column):
    """집계 접미사 제외 로직이 무관한 컬럼에 영향을 주지 않는다."""
    assert detect_pii([{column: "x"}]) == []


def test_pii_flags_team_members_as_group_of_people():
    """`team_members` 는 집계 접미사로 끝나지 않고, 개인(들)을 직접 가리키는 컬럼이다 —
    `member_count` 처럼 사람에 대한 숫자가 아니라 원본 개인정보(이름 목록 등)일 수 있으므로
    계속 감지 대상으로 둔다 (팀장이 이 판단을 명시적으로 요청함 — 어느 쪽이든 근거를 남길 것)."""
    warnings = detect_pii([{"team_members": "Alice, Bob"}])
    assert warnings, "team_members 는 사람 목록을 가리키므로 감지되어야 합니다"


# ── P2-2 픽스 2: 식별번호(`_num`)가 집계로 오인돼 빠지던 문제 ──
@pytest.mark.parametrize("column", [
    "buyer_num", "member_num", "reviewer_num", "user_num", "회원번호", "구매자번호",
])
def test_pii_flags_identifying_number_columns(column):
    """`num` 은 "인원 수" 가 아니라 "그 사람에게 매겨진 식별번호" 로 읽힐 수 있다 —
    `buyer_num`/`회원번호` 는 집계가 아니라 그 자체로 식별자이므로 감지되어야 한다."""
    warnings = detect_pii([{column: "x"}])
    assert warnings, f"식별번호 컬럼 '{column}' 을 감지하지 못했습니다"


@pytest.mark.parametrize("column", [
    "buyer_count", "member_count", "회원수", "구매자수",
])
def test_pii_still_ignores_real_aggregate_columns(column):
    """`_num` 회귀 수정이 진짜 집계 컬럼(`_count`/`수`)까지 다시 걸리게 하면 안 된다."""
    assert detect_pii([{column: "x"}]) == []


# ── P2-2 픽스 2: 사람을 가리키는 역할 명사 추가 (아이디는 이미 있었음) ──
@pytest.mark.parametrize("column", [
    "수신자", "담당자", "인수자", "접수자", "낙찰자",
])
def test_pii_detects_role_noun_columns(column):
    """작성자/구매자 외에도 사람을 직접 가리키는 역할 명사는 감지해야 한다."""
    warnings = detect_pii([{column: "x"}])
    assert warnings, f"역할 명사 컬럼 '{column}' 을 감지하지 못했습니다"


@pytest.mark.parametrize("column", [
    "숫자", "이자", "과자",
])
def test_pii_does_not_flag_unrelated_ja_ending_words(column):
    """'자' 로 끝나는 단어를 일괄로 잡지 않는다 — 리터럴 나열만 허용한다."""
    assert detect_pii([{column: "x"}]) == []


# ── P2-3: 부담 상한 ──
from utils import BudgetExceeded, RateLimiter


def test_delay_floor_is_enforced():
    """0 이나 음수로 사실상 무제한 요청을 내는 것을 막는다."""
    assert RateLimiter(delay=0).delay >= 0.5
    assert RateLimiter(delay=-1).delay >= 0.5


def test_backoff_still_doubles():
    limiter = RateLimiter(delay=1.0)
    limiter.backoff()
    assert limiter.delay == 2.0


def test_backoff_stops_after_consecutive_limit():
    """429 가 계속 오면 상대가 거절하고 있는 것이다 — 무한 백오프는 답이 아니다."""
    limiter = RateLimiter(delay=1.0, max_consecutive_errors=3)
    limiter.backoff()
    limiter.backoff()
    with pytest.raises(BudgetExceeded) as exc:
        limiter.backoff()
    assert "연속" in str(exc.value)


def test_success_resets_consecutive_counter():
    limiter = RateLimiter(delay=1.0, max_consecutive_errors=3)
    limiter.backoff()
    limiter.backoff()
    limiter.reset_errors()
    limiter.backoff()          # 리셋됐으므로 아직 여유가 있다
    assert limiter.delay == 8.0


def test_total_request_cap():
    limiter = RateLimiter(delay=0.5, max_requests=3)
    for _ in range(3):
        limiter.wait()
    with pytest.raises(BudgetExceeded) as exc:
        limiter.wait()
    assert "총 요청" in str(exc.value)


def test_no_cap_by_default():
    limiter = RateLimiter(delay=0.5)
    for _ in range(10):
        limiter.wait()
    assert limiter.request_count == 10


# ── S4: 값 검증 ──
from utils import validate_values

PRICE_SCHEMA = {
    "상품명": {"type": "str", "required": True, "max_empty_ratio": 0.1},
    "가격": {"type": "int", "required": True, "min": 1, "max": 100_000_000},
}


def test_valid_data_passes():
    data = [{"상품명": "사과", "가격": 3900}, {"상품명": "배", "가격": 5000}]
    assert validate_values(data, PRICE_SCHEMA) == []


def test_missing_required_field():
    issues = validate_values([{"상품명": "사과"}], PRICE_SCHEMA)
    assert any("가격" in i for i in issues)


def test_wrong_type():
    issues = validate_values([{"상품명": "사과", "가격": "삼천구백원"}], PRICE_SCHEMA)
    assert any("가격" in i and "타입" in i for i in issues)


def test_out_of_range():
    issues = validate_values([{"상품명": "사과", "가격": 0}], PRICE_SCHEMA)
    assert any("범위" in i for i in issues)


def test_empty_ratio_exceeded():
    data = [{"상품명": "", "가격": 100} for _ in range(9)] + [{"상품명": "사과", "가격": 100}]
    issues = validate_values(data, PRICE_SCHEMA)
    assert any("빈값" in i for i in issues)


def test_duplicate_ratio_flagged():
    """전부 같은 값이면 셀렉터가 엉뚱한 고정 요소를 잡은 것이다."""
    data = [{"상품명": "광고", "가격": 3900} for _ in range(20)]
    issues = validate_values(data, PRICE_SCHEMA)
    assert any("중복" in i for i in issues)


def test_empty_dataset_is_reported():
    assert validate_values([], PRICE_SCHEMA)


# ── S4 fix round 1: ITEM 1 — allow_uniform 면제 ──
UNIFORM_SCHEMA = {
    "카테고리": {"type": "str", "allow_uniform": True, "max_empty_ratio": 0.1},
}


def test_uniform_column_flags_without_opt_out():
    """카테고리처럼 균일해도 되는 필드조차, 면제를 안 걸면 여전히 경고한다 — 기본 동작 확인용."""
    data = [{"카테고리": "과일"} for _ in range(20)]
    issues = validate_values(data, {"카테고리": {"type": "str"}})
    assert any("중복" in i for i in issues)


def test_uniform_column_clean_with_opt_out():
    """allow_uniform=True 면 20건이 전부 같은 카테고리여도 조용하다."""
    data = [{"카테고리": "과일"} for _ in range(20)]
    assert validate_values(data, UNIFORM_SCHEMA) == []


def test_allow_uniform_only_exempts_the_duplicate_check():
    """allow_uniform 은 중복률 검사만 면제한다 — 같은 필드의 다른 검사는 그대로 걸려야 한다."""
    schema = {
        "카테고리": {"type": "str", "required": True, "max_empty_ratio": 0.1,
                    "allow_uniform": True},
    }
    data = [{"카테고리": ""} for _ in range(20)]
    issues = validate_values(data, schema)
    assert any("빈" in i for i in issues)          # 빈값 관련 검사는 여전히 걸린다
    assert not any("중복" in i for i in issues)     # 중복률 검사만 조용하다


# ── S4 fix round 1: ITEM 2 — required 가 빈 문자열도 누락으로 본다 ──
def test_required_flags_all_empty_strings_without_max_empty_ratio():
    """max_empty_ratio 를 안 걸어도, required=True 면 빈 문자열만 있는 필드는 잡혀야 한다."""
    data = [{"상품명": ""} for _ in range(10)]
    schema = {"상품명": {"type": "str", "required": True}}
    issues = validate_values(data, schema)
    assert issues
    assert any("상품명" in i for i in issues)


def test_required_treats_whitespace_only_as_empty():
    data = [{"상품명": "   "} for _ in range(10)]
    schema = {"상품명": {"type": "str", "required": True}}
    issues = validate_values(data, schema)
    assert issues


def test_required_passes_when_genuinely_populated():
    """중복률 검사와 뒤섞이지 않도록 값을 다양하게 둔다 — required 단독 동작만 본다."""
    data = [{"상품명": f"상품{i}"} for i in range(10)]
    schema = {"상품명": {"type": "str", "required": True}}
    assert validate_values(data, schema) == []


def test_required_missing_key_still_flagged():
    """기존 None 기반 케이스(키 자체가 없음)는 그대로 잡힌다 — 회귀 방지."""
    issues = validate_values([{"상품명": "사과"}], PRICE_SCHEMA)
    assert any("가격" in i for i in issues)


# ── 2026-08-21 실사이트 회귀 테스트에서 확인된 두 결함을 고정 ──
#   F1  3단 DynamicFetcher 가 조작된 Referer 를 보낸다 (google_search 기본 ON)
#   F11 전화번호 패턴이 구분자 없는 ID·URL 숫자열을 잡는다

from utils import DYNAMIC_KWARGS, plain_dynamic


# F1 — 사다리 A 는 3단에서도 출처를 지어내지 않는다

def test_dynamic_kwargs_disables_fabricated_referer():
    """google_search 는 Referer: https://www.google.com/ 를 붙인다 — 사다리 A 에서는 끈다.

    1·2단을 평문으로 만든 근거가 '조작된 출처' 였다. 3단도 통지 없이 도는 칸이므로 같은 기준이다.
    """
    assert DYNAMIC_KWARGS["google_search"] is False


def test_plain_dynamic_passes_google_search_false(monkeypatch):
    captured = {}

    class _FakeDynamicFetcher:
        @staticmethod
        def fetch(url, **kw):
            captured["url"] = url
            captured["kw"] = kw
            return "response"

    monkeypatch.setattr("scrapling.fetchers.DynamicFetcher", _FakeDynamicFetcher)

    assert plain_dynamic("https://example.com", network_idle=True) == "response"
    assert captured["url"] == "https://example.com"
    assert captured["kw"]["google_search"] is False
    assert captured["kw"]["network_idle"] is True


def test_plain_dynamic_allows_explicit_override(monkeypatch):
    """명시적으로 켜는 것은 막지 않는다 — 기본값을 정할 뿐이다."""
    captured = {}

    class _FakeDynamicFetcher:
        @staticmethod
        def fetch(url, **kw):
            captured.update(kw)
            return "response"

    monkeypatch.setattr("scrapling.fetchers.DynamicFetcher", _FakeDynamicFetcher)

    plain_dynamic("https://example.com", google_search=True)
    assert captured["google_search"] is True


# F11 — 전화번호 패턴이 ID·URL 을 잡지 않는다

@pytest.mark.parametrize("value", [
    "https://www.coupang.com/vp/products/8919133357",   # 상품ID 10자리 (30/30 오탐)
    "1000763360",                                       # kurly 상품번호 (23/24 오탐)
    "atchFileId=3af8fa2cf6e043d986f6d764664126ec",      # FSS 16진수 속 9자리 (6/36 오탐)
    "주문번호 20260821000123",                           # 14자리
    "3967600242987725422",                              # instagram pk 19자리
])
def test_phone_pattern_does_not_flag_ids_and_urls(value):
    """실측 오탐 — 세 도메인에서 ID·URL 만으로 경고가 쏟아졌고 실제 PII 는 0건이었다."""
    warnings = detect_pii([{"참조": value}])
    assert not any("전화번호" in w for w in warnings), f"오탐: {value!r} → {warnings}"


@pytest.mark.parametrize("value", [
    "010-1234-5678",
    "010.1234.5678",
    "010 1234 5678",
    "02-123-4567",
    "연락처는 031-888-9999 입니다",
])
def test_phone_pattern_still_flags_real_numbers(value):
    """구분자가 있는 실제 번호는 그대로 잡는다 — 오탐을 줄이려다 놓치면 안 된다."""
    warnings = detect_pii([{"메모": value}])
    assert any("전화번호" in w for w in warnings), f"놓침: {value!r}"


@pytest.mark.parametrize("value", ["01012345678", "01098765432"])
def test_phone_pattern_flags_bare_mobile_number(value):
    """구분자 없는 11자리 휴대폰은 형식이 명확하므로 잡는다."""
    warnings = detect_pii([{"메모": value}])
    assert any("전화번호" in w for w in warnings), f"놓침: {value!r}"


# --- CA 번들 (한글 경로 환경) ---
#
# 주의: pytest.ini 가 --basetemp=.tmp/pytest 라서 tmp_path 는 저장소 안에 생긴다.
# 저장소를 한글 폴더에 두면 tmp_path 자체가 비ASCII 라 여기서는 쓸 수 없다 —
# 경로의 ASCII 여부가 바로 이 테스트의 대상이기 때문이다. 그래서 시스템 임시 경로를 쓴다.

def _ascii_base():
    """ASCII 경로인 상위 디렉터리를 찾는다.

    conftest 가 tempfile.tempdir 을 저장소 안(.tmp)으로 고정하므로 mkdtemp() 를
    그냥 부를 수 없다 — 저장소가 한글 폴더면 그 결과도 한글이다. dir= 로 우회한다.
    """
    for base in (os.environ.get("LOCALAPPDATA"), os.environ.get("ProgramData"),
                 os.environ.get("TMPDIR"), "/tmp"):
        if base and str(base).isascii() and Path(base).is_dir():
            return base
    return None


@pytest.fixture
def ascii_dir():
    """ASCII 임이 보장된 작업 디렉터리."""
    base = _ascii_base()
    if base is None:
        pytest.skip("ASCII 경로인 상위 디렉터리를 찾지 못해 건너뜁니다")
    path = tempfile.mkdtemp(dir=base)
    try:
        yield Path(path)
    finally:
        shutil.rmtree(path, ignore_errors=True)


def _fake_certifi(monkeypatch, path):
    """certifi.where() 가 주어진 경로를 돌려주도록 만든다."""
    import certifi
    monkeypatch.setattr(certifi, "where", lambda: str(path))


def test_ca_bundle_untouched_when_path_is_ascii(monkeypatch, ascii_dir):
    """경로가 멀쩡하면 아무것도 하지 않는다 — 괜히 복사본을 만들지 않는다."""
    src = ascii_dir / "cacert.pem"
    src.write_bytes(b"x")
    monkeypatch.delenv("CURL_CA_BUNDLE", raising=False)
    _fake_certifi(monkeypatch, src)

    assert ensure_ascii_ca_bundle() is None
    assert "CURL_CA_BUNDLE" not in os.environ


def test_ca_bundle_copied_when_path_has_hangul(monkeypatch, ascii_dir):
    """한글 경로면 ASCII 위치로 복사하고 CURL_CA_BUNDLE 을 그리로 향하게 한다."""
    src_dir = ascii_dir / "한글폴더"
    src_dir.mkdir()
    src = src_dir / "cacert.pem"
    src.write_bytes(b"CERT-DATA")
    cache = ascii_dir / "cache"
    cache.mkdir()

    monkeypatch.delenv("CURL_CA_BUNDLE", raising=False)
    monkeypatch.delenv("SSL_CERT_FILE", raising=False)
    _fake_certifi(monkeypatch, src)
    monkeypatch.setattr("utils._ca_cache_candidates", lambda: [str(cache)])

    dest = ensure_ascii_ca_bundle()

    assert dest is not None
    assert Path(dest).read_bytes() == b"CERT-DATA"
    assert os.environ["CURL_CA_BUNDLE"] == dest
    dest.encode("ascii")  # ASCII 여야 libcurl 이 연다


def test_ca_bundle_respects_user_override(monkeypatch, ascii_dir):
    """사용자가 이미 지정했으면 존중한다 — 덮어쓰지 않는다."""
    src_dir = ascii_dir / "한글폴더"
    src_dir.mkdir()
    src = src_dir / "cacert.pem"
    src.write_bytes(b"x")
    monkeypatch.setenv("CURL_CA_BUNDLE", r"C:\my\own.pem")
    _fake_certifi(monkeypatch, src)

    assert ensure_ascii_ca_bundle() is None
    assert os.environ["CURL_CA_BUNDLE"] == r"C:\my\own.pem"
