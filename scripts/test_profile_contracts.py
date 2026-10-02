"""문서·docstring·프로필 데이터가 서로 어긋나는 지점을 CI 가 잡는다.

`test_doc_contracts.py` 가 잡는 것은 **문서가 코드를 속이는** 경우(없는 import,
없는 속성, 모르는 enum)다. 이 파일이 잡는 것은 그 반대 방향이다 — **코드/데이터가
문서를 속이는** 경우. 2026-09-27 실측 + 그날 독립 리뷰로 확인한 항목:

  #001 `domain_profile.py` 의 모듈 docstring 이 정본 문서보다 좁은 열거를 선언한다
  #002 CLAUDE.md·AGENTS.md 의 "7단계" 주장이 SKILL.md 실제 헤딩 수와 다르다
  #003 `builtini_co_kr` 가 커밋된 상태로 게이트 규칙 3(antibot_strategy 필수)을 어긴다
  #004 `g2b_go_kr` 의 notes 가 문자열이 아니라 문자열 배열이다
  #005 (없음 — 취소. 지워진 문서가 검토 전에 이미 정리됐다)
  #006 `detect_softblock` 의 min_size 기본값이 JSON API 를 오탐하는데 Step 5.0 이
       이를 말하지 않는다
  #007 `notes`·`pagination.type` 계약이 docstring 과 정본 문서에서 다르다
  #008 Step 5.0 스니펫이 미정의 이름을 쓴다 / 판정 대상과 넘긴 본문이 다르다

#001 은 특히 위험하다. docstring 은 사용자가 실제로 `import` 하는 모듈에 붙어 있어서
문서를 따랐는데 저장이 `ConsentRequired` 로 거부되는, `test_doc_contracts.py` 의
enum 검사와 **같은 함정을 다른 문서에서 재발**시킨다.

전부 프로필/문서를 **읽기만** 한다. 네트워크를 타지 않고 save() 도 호출하지 않는다.
"""
import ast
import json
import pathlib
import re

import pytest

REPO = pathlib.Path(__file__).resolve().parent.parent

# 정본 문서 (Step 5-A 게이트가 있는 곳). .codex 는 생성 미러이므로 보지 않는다.
SKILL_MD = REPO / ".claude/skills/web-crawler/SKILL.md"
CLAUDE_MD = REPO / "CLAUDE.md"
# 2026-10-02 — CLAUDE.md 의 프로필 스키마 열거·notes 템플릿은 docs/crawl-reference.md 로
# 옮겼다. 정본 열거 소스에 이 문서를 넣지 않으면 옮긴 블록이 갱신돼도 검사가 못 본다.
CRAWL_REF = REPO / "docs/crawl-reference.md"
AGENTS_MD = REPO / "AGENTS.md"
DOMAIN_PROFILE_PY = REPO / "scripts/domain_profile.py"
FINGERPRINTS = REPO / "fingerprints"

# 열거를 선언하는 필드.
#
# `capability` 는 4개로 고정이라 열거 표기가 없고, `distribution` 은 자유 서술이라
# 검사하지 않는다. 나머지는 정본 문서가 `<a|b|c>` 형태로 제시한다.
#
# 다만 **강제력이 다르다** — `profile_policy._FIELDS` 는 `("fetcher_type",
# "antibot_strategy")` 뿐이다. 이 둘은 모르는 값이면 `save()` 가 `ConsentRequired` 로
# 막는다(게이트 규칙 5). 반면 `site_type`·`antibot_type` 은 분류기가 보지 않으므로
# 미선언 값이어도 저장은 통과한다 — 그래서 그 둘에 대한 검사는 "값의 통제" 가 아니라
# "docstring 에 필드 자체가 적혀 있는가" 로 약하게 건다.
ENUM_FIELDS = ("fetcher_type", "antibot_type", "antibot_strategy", "site_type")
# 분류기가 실제로 강제하는 필드 — 여기만 닫힌 열거로 건다.
ENFORCED_FIELDS = ("fetcher_type", "antibot_strategy")

# `"fetcher_type": "<a|b|c>"` — Step 5-A 가 저장 契约으로 제시하는 열거.
_ENUM_LINE = re.compile(r'"(fetcher_type|antibot_type|antibot_strategy|site_type)"\s*:\s*"<([^">]+)>"')
# docstring 은 구분자가 `|` 이고 있어도 되고 없어도 된다 (구버전 L10 이 `|` 없이 적었다).
_PLAIN_ENUM_LINE = re.compile(
    r'"(fetcher_type|antibot_type|antibot_strategy|site_type)"\s*:\s*"([^"<>=]+)"'
)


def _split(body: str) -> set[str]:
    return {v.strip() for v in body.split("|") if v.strip()}


# ── #001 docstring 열거 ↔ 정본 문서 열거 ──────────────────────────────────

def _docstring_enums() -> dict[str, set[str]]:
    """domain_profile.py 모듈 docstring 이 선언한 fetcher_type/antibot_strategy."""
    tree = ast.parse(DOMAIN_PROFILE_PY.read_text(encoding="utf-8"))
    out: dict[str, set[str]] = {}
    for field, body in _PLAIN_ENUM_LINE.findall(ast.get_docstring(tree) or ""):
        out.setdefault(field, set()).update(_split(body))
    return out


def _authoritative_enums() -> dict[str, set[str]]:
    """SKILL.md + crawl-reference.md 가 제시하는 열거 (합집합)."""
    out: dict[str, set[str]] = {}
    for path in (SKILL_MD, CRAWL_REF):
        for field, body in _ENUM_LINE.findall(path.read_text(encoding="utf-8")):
            out.setdefault(field, set()).update(_split(body))
    return out


DOCSTRING_ENUMS = _docstring_enums()
AUTHORITATIVE_ENUMS = _authoritative_enums()


def test_enum_extraction_is_not_empty():
    """수집기가 0개를 훑고 조용히 통과하는 상태를 막는다."""
    assert AUTHORITATIVE_ENUMS.get("fetcher_type"), "정본 문서에서 fetcher_type 열거를 못 찾았다"
    assert DOCSTRING_ENUMS.get("fetcher_type"), "domain_profile.py docstring 열거를 못 읽었다"


@pytest.mark.parametrize("field", ENUM_FIELDS)
def test_docstring_declares_enum_field(field):
    """스키마를 담은 유일한 문서인 docstring 은 이 필드들을 선언해야 한다.

    `site_type` 은 docstring 에 아예 없었다 — `scripts/domain_profile.py` 의 프로필
    스키마 목록을 읽는 사람이 그 필드의 존재 자체를 몰랐다.
    """
    assert field in DOCSTRING_ENUMS, (
        f"domain_profile.py docstring 의 프로필 스키마에 `{field}` 가 없다. "
        f"정본 문서는 이 필드를 열거하고 있다: {sorted(AUTHORITATIVE_ENUMS.get(field, []))}"
    )


@pytest.mark.parametrize("field", ENFORCED_FIELDS)
def test_docstring_enum_is_not_narrower_than_authoritative_docs(field):
    """docstring 이 정본 문서보다 좁으면 안 된다.

    좁으면 그 모듈을 읽은 사람이 정본에 있는 값을 알 수 없다.

    강제 필드(`ENFORCED_FIELDS`)에 한정한다. `site_type`·`antibot_type` 은 분류기가
    보지 않으므로 좁은 docstring 이 저장을 막지는 않지만, 그래도 정본과 어긋나면 안 된다.
    그쪽 결손(예: docstring 에 없던 `spa_session` 을 커밋된 `g2b_go_kr` 가 쓰고 있었다)은
    `test_docstring_declares_enum_field` 가 잡는다 — 필드 자체가 선언돼 있었는지를 본다.
    """
    missing = AUTHORITATIVE_ENUMS[field] - DOCSTRING_ENUMS[field]
    assert not missing, (
        f"domain_profile.py docstring 의 `{field}` 열거에 정본 문서보다 좁다. "
        f"누락: {sorted(missing)}\n"
        f"  정본 문서: {sorted(AUTHORITATIVE_ENUMS[field])}\n"
        f"  docstring : {sorted(DOCSTRING_ENUMS[field])}"
    )


@pytest.mark.parametrize("field", ["fetcher_type", "antibot_strategy"])
def test_docstring_enum_values_are_known_to_classifier(field):
    """docstring 이 적는 값은 분류기가 알아듣는 값이어야 한다 (기존 enum 검사와 같은 방향)."""
    from profile_policy import TOOLS, _norm

    unknown = sorted(v for v in DOCSTRING_ENUMS.get(field, set()) if _norm(v) not in TOOLS)
    assert not unknown, f"docstring 의 `{field}` 값 중 분류기가 모르는 것: {unknown}"


# ── #002 "N단계" 주장이 실제 SKILL.md 구조와 일치하는가 ─────────────────────

_STEP_HEADING = re.compile(r"^#{2,3} Step ([0-9]+(?:-[A-Z0-9]+|\.[0-9]+)?)\b", re.M)


def _skill_md_step_labels() -> list[str]:
    return _STEP_HEADING.findall(SKILL_MD.read_text(encoding="utf-8"))


def test_step_heading_extraction_is_not_empty():
    labels = _skill_md_step_labels()
    assert len(labels) >= 10, f"SKILL.md Step 헤딩이 {len(labels)}개뿐 — 수집기가 깨졌을 수 있다"


@pytest.mark.parametrize("doc", [CLAUDE_MD, AGENTS_MD], ids=lambda p: p.name)
def test_documented_step_count_is_not_contradicted(doc):
    """문서가 주장하는 단계 수가 실제 헤딩 수와 어긋나면 안 된다.

    "7단계" 같은 단일 숫자는 SKILL.md 가 표를 늘릴 때마다 조용히 거짓이 된다.
    그래서 **개수를 세지 말고 구조를 가리키도록** 문장을 고친다.
    """
    text = doc.read_text(encoding="utf-8")
    m = re.search(r"(\d+)\s*단계", text)
    if not m:
        return  # 개수를 주장하지 않으면 이 검사 대상이 아니다
    claimed = int(m.group(1))
    actual = len(_skill_md_step_labels())
    assert claimed == actual, (
        f"{doc.name}:{text[:m.start()].count(chr(10)) + 1} 이 워크플로우를 '{claimed}단계' 라고 "
        f"하지만 SKILL.md 의 Step 헤딩은 {actual}개다 "
        f"({', '.join(_skill_md_step_labels())}). "
        f"개수를 세는 대신 SKILL.md 를 가리키도록 문장을 고쳐라 — 표가 늘어나면 숫자가 또 거짓이 된다"
    )


# ── #003/#004 커밋된 프로필이 SKILL.md Step 5-A 게이트 규칙을 지키는가 ───────
# 게이트 규칙 3: "fetcher_type / antibot_strategy 둘은 무조건 채운다... 빈 값이면
# 게이트 기능을 못 한다". 규칙 1: "notes 필드는 비워두지 않는다".

def _committed_profiles() -> list[tuple[str, dict]]:
    out = []
    for path in sorted(FINGERPRINTS.glob("*/profile.json")):
        out.append((path.parent.name, json.loads(path.read_text(encoding="utf-8"))))
    return out


PROFILES = _committed_profiles()


def test_profiles_were_collected():
    assert len(PROFILES) >= 10, f"프로필이 {len(PROFILES)}개뿐 — 수집기가 깨졌을 수 있다"


# 커밋된 데이터가 정본 열거 안에 있는가
# `site_type` 은 분류기가 보지 않으므로 미선언 값이 조용히 통과한다. 그 결과 문서가
# 5값만 적고 실제로는 8종이 쓰이는 상태가 오래 유지됐다. 정본 열거를 실제 값에 맞춰
# 넓혔으므로(2026-09-27) 이제부터 새 값이 생기면 여기서 걸린다.

UNCLASSIFIED_ENUM_FIELDS = ("site_type", "antibot_type")


@pytest.mark.parametrize("field", UNCLASSIFIED_ENUM_FIELDS)
@pytest.mark.parametrize("name,profile", PROFILES, ids=[n for n, _ in PROFILES])
def test_committed_profile_unclassified_enum_is_documented(name, profile, field):
    """커밋된 프로필의 기술 라벨이 정본 문서 열거에 들어가는가.

    분류기가 보지 않는 필드라 저장엔 영향이 없지만, 문서가 실제 어휘를 모르면
    다음 사람이 또 새 라벨을 만들어 두 어휘가 된다.
    """
    value = profile.get(field)
    if value is None:
        return
    documented = AUTHORITATIVE_ENUMS[field]
    assert value in documented, (
        f"{name}: `{field}` = {value!r} 가 정본 문서 열거에 없다. "
        f"정본: {sorted(documented)}\n"
        f"  실제로 쓰이는 값을 정본에 추가하거나, 이 프로필의 값을 정본에 맞게 고쳐라"
    )


@pytest.mark.parametrize("name,profile", PROFILES, ids=[n for n, _ in PROFILES])
@pytest.mark.parametrize("field", ["fetcher_type", "antibot_strategy"])
def test_committed_profile_fills_strategy_fields(name, profile, field):
    """게이트 규칙 3 — 두 필드는 비울 수 없다.

    결측이 조용히 통과하는 이유는 `get_antibot_strategy()` 가 기본값 `'none'` 을
    돌려주기 때문이다. 그래서 **기본값이 아니라 데이터**를 검사한다.
    """
    value = profile.get(field)
    assert value, (
        f"{name}: `{field}` 가 비어 있다 — SKILL.md Step 5-A 게이트 규칙 3 위반. "
        f"DomainProfile.get_antibot_strategy() 는 이 결측을 'none' 으로 덮어서 "
        f"오탐 없이 넘어가지만, 다음 세션이fetcher chain 을 잘못 건너뛴다"
    )


@pytest.mark.parametrize("name,profile", PROFILES, ids=[n for n, _ in PROFILES])
def test_committed_profile_notes_is_deterministic_brief(name, profile):
    """게이트 규칙 1 — notes 는 비어있지 않은 str 또는 list[str].

    배열을 허용하는 이유: 게이트 규칙 6이 "notes 를 누적/수정한다" 고 요구하므로
    여러 줄이 쌓인 배열도 유효하다. 문자열로 강제하면 실제로 모은 지식이 파괴된다.
    """
    notes = profile.get("notes")
    assert notes, f"{name}: `notes` 가 비어 있다 — SKILL.md Step 5-A 게이트 규칙 1 위반"
    if isinstance(notes, list):
        assert all(isinstance(n, str) and n.strip() for n in notes), (
            f"{name}: `notes` 배열에 빈 문자열이 섞여 있다 — 정찰 없이 수집할 수 있는 "
            f"결정적 정보가 아니어야 한다"
        )
    else:
        assert isinstance(notes, str), (
            f"{name}: `notes` 가 {type(notes).__name__} 이다. "
            f"스키마(docstring)는 `str | list[str]` 다"
        )


@pytest.mark.parametrize("name,profile", PROFILES, ids=[n for n, _ in PROFILES])
def test_committed_profile_api_endpoints_follow_schema(name, profile):
    """`api_endpoints` 는 스키마대로 객체 배열이다.

    문자열("GET https://...") 으로 적은 항목은 `field_mapping` 을 담을 자리가 없어서
    Step 3.5 필드 매핑의 결과가 사라진다.
    """
    endpoints = profile.get("api_endpoints")
    if endpoints is None:
        pytest.skip(f"{name}: api_endpoints 없음 (정찰 단계 미도달 프로필)")
    assert isinstance(endpoints, list), (
        f"{name}: `api_endpoints` 가 {type(endpoints).__name__} 이다 — 스키마는 list 다"
    )
    bad = [e for e in endpoints if not isinstance(e, dict)]
    assert not bad, (
        f"{name}: `api_endpoints` 안에 문자열이 있다: {bad}\n"
        f"  스키마: [{{'url': '', 'method': 'GET', 'params': {{}}, 'field_mapping': {{}}}}]"
    )


# ── #007 `notes`·`pagination.type` 계약이 정본 문서와 어긋난다 ─────────────
# 2026-09-27 독립 리뷰 [경] 2건. 둘 다 "코드/데이터는 맞는데 정본 문서가 옛말을 하는" 형태.


def _doc_notes_template_lines() -> list[tuple[str, str]]:
    """(문서, `"notes":` 템플릿 줄) 목록."""
    out = []
    for path in (CLAUDE_MD, CRAWL_REF, SKILL_MD):
        for line in path.read_text(encoding="utf-8").splitlines():
            if '"notes"' in line and ":" in line and "<" in line:
                out.append((path.name, line.strip()))
    return out


def test_authoritative_docs_allow_list_valued_notes_when_a_profile_uses_one():
    """notes 를 배열로 쓰는 프로필이 있으면 정본 템플릿도 배열을 허용해야 한다.

    `g2b_go_kr` 는 실제로 `notes` 를 문자열 배열 10개로 저장한다(게이트 규칙 6의 누적 요구).
    그런데 정본 템플릿은 "한두 줄"만 말해 두 정본이 서로 다른 타입을 말한다 — 무엇을
    써야 맞는지는 문서를 읽는 사람이 추측해야 한다.
    """
    list_users = [
        name for name, p in PROFILES if isinstance(p.get("notes"), list)
    ]
    if not list_users:
        pytest.skip("배열형 notes 를 쓰는 프로필이 없다 — 계약 정합을 확인할 대상이 없다")

    stale = [
        (doc, line) for doc, line in _doc_notes_template_lines()
        if "list" not in line.lower() and "배열" not in line
    ]
    assert not stale, (
        f"notes 를 배열로 쓰는 프로필이 {list_users} 인데 정본 템플릿은 단일 문자열만 말한다:\n"
        + "\n".join(f"  {doc}: {line}" for doc, line in stale)
        + "\n  domain_profile.py docstring 은 이미 `str | list[str]` 라고 적었다 — 정본을 맞춰라"
    )


def test_committed_pagination_type_is_declared_in_docstring():
    """커밋된 프로필의 `pagination.type` 이 docstring 에 선언돼야 한다.

    실측 분포(2026-09-27): 전체 14개 중 `pagination` 을 가진 것이 12개 —
    url_param 4, url_path 3, none_latest_n 1, toc_tree 1, category_param 1, offset 1, query_param 1.
    옛 docstring 은 `url_param|next_button|infinite_scroll` 3값뿐이었고, 그중
    `next_button`·`infinite_scroll` 은 **쓰는 프로필이 하나도 없다**.
    """
    docstring = ast.get_docstring(ast.parse(DOMAIN_PROFILE_PY.read_text(encoding="utf-8"))) or ""
    # pagination 은 중첩이라 _PLAIN_ENUM_LINE 으로는 안 잡힌다 — 한 줄을 직접 읽는다.
    m = re.search(r'"pagination"\s*:\s*\{[^}]*?"type"\s*:\s*"([^"]+)"', docstring)
    assert m, "domain_profile.py docstring 의 pagination.type 열거를 못 읽었다"
    declared = _split(m.group(1))

    used = {
        (p.get("pagination") or {}).get("type")
        for _, p in PROFILES
        if isinstance(p.get("pagination"), dict)
    }
    used.discard(None)
    missing = sorted(used - declared)
    assert not missing, (
        f"커밋된 프로필이 쓰는 `pagination.type` 중 docstring 에 없는 값: {missing}\n"
        f"  사용 중: {sorted(used)}\n"
        f"  docstring: {sorted(declared)}"
    )


# ── #006 detect_softblock 의 min_size 가 JSON API 를 오탐한다 ──────────────
# 2026-09-27 실측: 유효한 리뷰 API 응답 858B 가 verdict="challenge", blocked=True 로 판정됐다.
# 시그널은 "response too small: 858B < 3000B" 하나였고, 그 응답은 실제로 HTTP 200 + 정상 JSON 이었다.
#
# `min_size` 는 **HTML 페이지** 휴리스틱이다. 게이트를 약화시키지 않는 해법은 하나뿐이다 —
# **호출자가 본문 종류에 맞춰 min_size 를 준다.** 그래서 여기서는 두 가지를 건다.
#   ① 동작 계약: 호출자가 min_size 를 주면 유효한 소형 JSON 이 통과한다(로직을 안 바꾸고도).
#   ② 문서 계약: SKILL.md Step 5.0 이 그 방법을 알려줘야 한다 — 모르면 아무도 안 준다.

VALID_API_JSON = json.dumps({
    "reviews": [{"author": "김지*", "created_at": "2026/09/27", "message": "좋아요"}],
    "reviews_count": 1,
})


def test_small_valid_json_is_not_a_softblock_when_min_size_is_set():
    """호출자가 min_size 를 주면 유효한 소형 JSON 은 통과한다 — 게이트 로직은 그대로.

    이 검사가 규칙 ①의 근거다. `detect_softblock` 를 고치지 않아도 호출 쪽에서 해결된다는
    것을 고정한다. (기본값 3000 이면 실제로 blocked=True 가 된다 — 아래 검사가 이를 상기시킨다)
    """
    from utils import detect_softblock

    verdict = detect_softblock(VALID_API_JSON, status=200, min_size=0)
    assert verdict["blocked"] is False, (
        f"min_size=0 인데 유효한 JSON 이 차단됐다: {verdict} — 게이트 로직이 바뀌었으면 "
        f"이 테스트는 통과시키려고 로직을 건드리는 방향으로 오해된다"
    )
    assert verdict["verdict"] in ("strong_ok", "weak_ok"), verdict


def test_default_min_size_rejects_small_json_so_the_trap_is_visible():
    """기본 min_size=3000 이 소형 JSON 을 거절한다는 사실을 문서로 새긴다.

    이건 "그래야 한다" 가 아니라 **현재 동작을 못 박는** 검사다. 나중에 게이트를 고치면
    이 테스트가 먼저 깨져서 그 사실을 숨기지 못하게 한다.
    """
    from utils import detect_softblock

    verdict = detect_softblock(VALID_API_JSON, status=200)
    assert verdict["blocked"] is True, (
        "detect_softblock 의 기본 min_size 가 더 이상 소형 JSON 을 거절하지 않는다 — "
        "그게 좋아졌다면 SKILL.md Step 5.0 와 이 테스트를 함께 갱신하라"
    )
    assert any("too small" in s for s in verdict["signals"]), verdict["signals"]


def test_skill_md_step_5_0_tells_callers_to_set_min_size_for_json():
    """SKILL.md Step 5.0 이 JSON API 에 min_size 를 주라고 알려줘야 한다.

    게이트를 약화시키지 않는 해법은 호출자 지정뿐인데, 문서가 그걸 말 안 하면 아무도 안 준다.
    호출 예시 검사는 정규식이 아니라 `ast` 로 한다 — 인자에 `bool(page.css(...))` 처럼
    괄호가 여러 겹 중첩돼 있어 정규식은 조용히 실패한다(문서가 틀렸는데 검사가 그 탓을 하므로).
    """
    text = SKILL_MD.read_text(encoding="utf-8")
    start = text.index("### Step 5.0")
    end = text.index("## Step 5-A")
    section = text[start:end]

    assert "min_size" in section, (
        "SKILL.md Step 5.0 이 min_size 를 언급하지 않는다 — JSON API 를 수집하면 "
        "정상 응답이 'response too small' 신호로 소프트블록이 된다"
    )

    calls = []
    for block in re.findall(r"^```python\n(.*?)^```", section, re.S | re.M):
        try:
            tree = ast.parse(block)
        except SyntaxError:
            continue  # 자리표시자가 있는 블록은 해석 불가 — 다른 블록으로
        calls.extend(
            node for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "detect_softblock"
        )

    assert calls, (
        "SKILL.md Step 5.0 에서 detect_softblock 호출을 못 찾았다 — "
        "수집기가 깨졌거나 예시가 사라졌다"
    )
    missing = [c for c in calls if "min_size" not in {k.arg for k in c.keywords}]
    assert not missing, (
        f"SKILL.md Step 5.0 의 detect_softblock 호출 {len(missing)}건에 min_size 인자가 없다 — "
        f"설명과 예제가 어긋난다. 기본 3000B 은 HTML 기준이라 JSON API 를 오탐한다"
    )


# 스니펫이 '문서대로 하면 죽는 코드' 를 다시 들여오지 않게 한다.
#
# `test_doc_contracts.py` 는 import 대상과 래퍼 속성만 본다. **미정의 지역변수** 는
# 그 어느 쪽도 잡지 않는다. 2026-09-27 독립 리뷰가 정확히 이걸 찾았다 —
# Step 5.0 스니펫이 `isinstance(data, (dict, list))` 를 썼는데 같은 블록에 `data =` 가 없다.
# 복사하면 NameError 로 죽고, 설령 Step 5 관례대로 수집 결과 리스트로 해석되더라도
# 리스트는 언제나 (dict, list) 의 인스턴스라 **HTML 수집에도 min_size=0 이 걸린다** —
# 문서가 지키려던 "빈 셸" 크기 신호가 꺼진다. 문서 한 줄이 안전 게이트를 약화시킨 셈이다.

# Step 5.0 스니펫이 참조해도 되는 외부 이름. 여기 없는 이름은 블록 안에서 정의되어야 한다.
# `data`·`results` 는 수집 결과라 정당한 외부값이다 — 문제는 이름이 아니라 **무엇을 판정하느냐**다.
# (아래 test_step_5_0_judges_the_body_it_passes 가 그것을 이름에 의존하지 않고 잡는다)
STEP_5_0_ALLOWED_FREES = {
    # 런타임 객체
    "page", "resp", "response", "session", "logger", "data", "results", "issues",
    # 임포트/함수
    "detect_softblock", "detect_pii", "validate_values", "hasattr", "bool", "dict",
    "int", "len", "str",
    # 지역 변수
    "verdict", "is_json_api", "body", "html", "text",
}


def _step_5_0_python_blocks() -> list[str]:
    text = SKILL_MD.read_text(encoding="utf-8")
    section = text[text.index("### Step 5.0"):text.index("## Step 5-A")]
    return re.findall(r"^```python\n(.*?)^```", section, re.S | re.M)


def test_step_5_0_snippet_has_no_undefined_names():
    """Step 5.0 스니펫의 자유 이름은 선언된 외부 이름이거나 블록 안에서 정의돼야 한다."""
    unresolved = {}
    for block in _step_5_0_python_blocks():
        try:
            tree = ast.parse(block)
        except SyntaxError:
            continue
        bound = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del)):
                bound.add(node.id)
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                bound.add(node.name)
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    a = node.args
                    for arg in [*a.posonlyargs, *a.args, *a.kwonlyargs, a.vararg, a.kwarg]:
                        if arg is not None:
                            bound.add(arg.arg)
            elif isinstance(node, (ast.Import, ast.ImportFrom)):
                for alias in node.names:
                    bound.add((alias.asname or alias.name).split(".")[0])
            elif isinstance(node, ast.ExceptHandler) and node.name:
                bound.add(node.name)
        free = {n.id for n in ast.walk(tree)
                if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)} - bound
        unknown = free - STEP_5_0_ALLOWED_FREES
        if unknown:
            unresolved.update({k: sorted(unknown) for k in ["free"]})
    assert not unresolved, (
        f"Step 5.0 스니펫이 선언되지 않은 이름을 쓴다: {sorted(unresolved.get('free', []))}\n"
        f"  외부 이름은 STEP_5_0_ALLOWED_FREES 에, 또는 블록 안에서 정의해야 한다. "
        f"문서를 그대로 복사하면 NameError 로 죽는다"
    )


def _root_name(node: ast.AST) -> str | None:
    """표현식의 뿌리 이름. `body.lstrip()[:1]` 이면 'body'."""
    while True:
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, (ast.Attribute, ast.Subscript)):
            node = node.value
        elif isinstance(node, ast.Call):
            node = node.func
        else:
            return None


def test_step_5_0_judges_the_body_it_passes():
    """JSON 판정 대상이 detect_softblock 에 넘긴 본문과 **같은 것**이어야 한다.

    `isinstance(data, (dict, list))` 는 수집 결과 리스트에 대해 **항상 True** 다.
    그 결과 HTML 수집에도 min_size=0 이 적용되어 빈 셸 신호가 꺼진다 —
    즉 문서 한 줄이 안전 게이트를 약화시킨다.

    판정에 쓰이는 **어떤 표현식이든** 잡아야 하므로 특정 호출 모양(isinstance 등)으로
    열거하지 않는다. min_size 인자식에 등장하는 이름 전부를 판정 근거로 모은 뒤
    넘긴 본문의 뿌리 이름과 대조한다. 2026-09-27 독립 리뷰가 이 사각을 찾았다 —
    isinstance 만 보던 검사는 `body.lstrip()[:1] in (...)` 형태에서 아무것도 하지 않았다.
    """
    for block in _step_5_0_python_blocks():
        try:
            tree = ast.parse(block)
        except SyntaxError:
            continue
        detect_call = None
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                    and node.func.id == "detect_softblock" and node.args):
                detect_call = node
        if detect_call is None:
            continue

        passed = _root_name(detect_call.args[0])
        if passed is None:
            continue

        # is_json_api 값에 등장하는 모든 이름 = JSON 판정에 쓰인 이름
        judged: set[str] = set()
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Assign) and len(node.targets) == 1
                    and isinstance(node.targets[0], ast.Name)
                    and node.targets[0].id == "is_json_api"):
                continue
            for sub in ast.walk(node.value):
                if isinstance(sub, ast.Name):
                    judged.add(sub.id)
                elif isinstance(sub, ast.Call) and isinstance(sub.func, ast.Name) \
                        and sub.func.id in ("isinstance", "str", "list", "dict", "len"):
                    judged.add(sub.func.id)

        offenders = {n for n in judged if _root_name(ast.Name(id=n)) != passed
                     and n not in ("str", "list", "dict", "len")}
        assert not offenders, (
            f"Step 5.0 이 {sorted(offenders)} 로 JSON 을 판정하지만 detect_softblock 에는 "
            f"{passed!r} 를 넘긴다 — 판정 대상과 실제 본문이 다르다\n"
            f"  수집 결과(리스트)는 판정이 언제나 참이 되어 HTML 수집에도 min_size=0 이 걸리고 "
            f"'빈 셸' 크기 신호가 꺼진다. 넘기는 그 본문으로 판정하라"
        )
