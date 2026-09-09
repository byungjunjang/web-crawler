"""프로필 배포 정책 — 우회 레시피가 배포에 섞이지 않는지 검사."""
import pytest

from profile_policy import (distribution, is_distributable, is_unrecognized_tool,
                             ladder_rung, load_all, public_dirs)


# ── 정규화: 같은 것을 두 표기로 쓰고 있다 (chrome_cdp / CDP) ──
@pytest.mark.parametrize("value", ["chrome_cdp", "CDP", "Chrome CDP", "chromeCDP", "cdp"])
def test_cdp_spellings_all_reach_rung_six(value):
    assert ladder_rung({"fetcher_type": value}) == 6


def test_ladder_a_tools():
    assert ladder_rung({"fetcher_type": "Fetcher"}) == 1
    assert ladder_rung({"fetcher_type": "FetcherSession"}) == 2
    assert ladder_rung({"fetcher_type": "API_SESSION"}) == 2
    assert ladder_rung({"fetcher_type": "DynamicFetcher"}) == 3


def test_ladder_b_tools():
    assert ladder_rung({"antibot_strategy": "stealthy"}) == 5
    assert ladder_rung({"fetcher_type": "StealthyFetcher"}) == 5


def test_unknown_tool_is_rung_zero():
    """모르는 도구는 판별 불가(0) — distribution 이 default-deny 로 받는다."""
    assert ladder_rung({"fetcher_type": "SomeNewBypassTool"}) == 0


def test_naver_antibot_reaches_rung_six():
    """네이버 계열 안티봇도 실제 크롬 세션이 필요하다 — 6단으로 분류된다."""
    assert ladder_rung({"antibot_strategy": "naver_antibot"}) == 6
    assert distribution({"antibot_strategy": "naver_antibot"}) == "local"


def test_stealthy_session_reaches_rung_five():
    assert ladder_rung({"antibot_strategy": "stealthy_session"}) == 5


# ── ITEM 1: 저장소 문서가 이미 쓰는 이름들을 사다리가 인식하는가 ──
@pytest.mark.parametrize("value,expected_rung", [
    ("DynamicSession", 3),           # SKILL.md 무한 스크롤 절
    ("PlaywrightFetcher", 3),        # DynamicFetcher 의 옛 이름
    ("playwright_sync_api", 3),      # 절대 규칙 1 예외 문구
    ("Spider", 3),                   # CLAUDE.md 500건+ 권고
])
def test_documented_ladder_a_names_are_recognized(value, expected_rung):
    assert ladder_rung({"fetcher_type": value}) == expected_rung


@pytest.mark.parametrize("value", ["yt-dlp", "RSS", "oEmbed", "Jina"])
def test_phase_zero_routes_are_rung_one_not_unknown(value):
    """Phase 0 공인 우회로는 사다리 A 의 가장 낮은 칸이다 — 0(미상)이 아니라 1이어야 한다.

    0을 썼다면 '모르겠다' 는 뜻이 되어 distribution() 이 default-deny 로 묶어버린다.
    Phase 0 경로는 알려진 값이고 공개해도 되는 사다리 A 이므로 1이 맞다."""
    assert ladder_rung({"fetcher_type": value}) == 1
    assert distribution({"fetcher_type": value}) == "public"


# ── 레지스트리 자체의 불변식 ────────────────────────────────────────────────
#
# 예전에는 이름→칸 표와 이름→능력 표가 따로 있었고, 여기 있던 테스트는 두 표의 키 집합이
# 같은지를 봤다(한쪽에만 있는 이름이 실제로 배포된 전례가 있었다). 표가 하나로 합쳐진
# 지금 그 어긋남은 구조적으로 불가능하다 — 행 하나에 칸과 능력이 함께 들어 있으므로
# 이름이 한쪽에만 존재할 수가 없다. 그래서 그 검사는 의미가 없어졌고, **여전히 가능한
# 어긋남**으로 바꿔 건다: 행은 있는데 그 행의 능력 칸이 비었거나(None) 오타인 경우.
# infer_capability 는 그때 조용히 None 을 낸다 — 사다리 값은 인식되면서 능력만 사라진다.
def test_every_ladder_tool_declares_a_capability():
    """사다리에 앉은 도구(rung >= 1)는 반드시 능력을 함께 선언해야 한다."""
    from profile_policy import TOOLS
    missing = sorted(name for name, (rung, cap, _) in TOOLS.items() if rung >= 1 and cap is None)
    assert missing == [], f"capability 가 비어 있는 사다리 도구: {missing}"


def test_registry_capabilities_are_all_valid():
    """능력 칸은 CAPABILITIES 안의 값이거나 None(중립값) 이어야 한다 — 오타가 조용히 살면
    infer_capability 가 스키마에 없는 값을 프로필에 써넣는다."""
    from profile_policy import CAPABILITIES, TOOLS
    bad = sorted({cap for _, cap, _ in TOOLS.values() if cap is not None and cap not in CAPABILITIES})
    assert bad == [], f"CAPABILITIES 에 없는 능력 값: {bad}"


def test_registry_rungs_are_in_range():
    """칸은 0(칸 없음) 또는 1~6 이다. 7 단은 없고, 음수는 max() 계산을 조용히 뒤집는다."""
    from profile_policy import TOOLS
    bad = sorted(name for name, (rung, _, _) in TOOLS.items() if rung not in range(0, 7))
    assert bad == [], f"사다리 범위를 벗어난 rung: {bad}"


def test_withheld_tools_cannot_be_neutral():
    """빼기로 한 도구가 중립값 자리에 들어가면(능력 None) '대응 없음' 과 구분이 사라진다."""
    from profile_policy import TOOLS
    bad = sorted(name for name, (_, cap, withheld) in TOOLS.items() if withheld and cap is None)
    assert bad == [], f"withheld 인데 능력이 비어 있는 도구: {bad}"


# ── is_unrecognized_tool: ladder_rung 이 0 으로 뭉개는 두 경우를 구분한다 ──
@pytest.mark.parametrize("profile", [
    # 한쪽 필드가 인식되는 rung-6 값이어도, 다른 필드가 모르는 값이면 ladder_rung 은 그
    # 신호를 버리고 0 을 낸다(첫 미상에서 즉시 return) — is_unrecognized_tool 은 버려지지
    # 않고 이 조합을 잡아야 한다.
    {"fetcher_type": "chrome_cdp", "antibot_strategy": "some_typo_value"},
    {"fetcher_type": "fetch_via_grid"},
    {"fetcher_type": "StealthyFetcher(solve_cloudflare=True)"},
    {"fetcher_type": "CDP (headed)"},
])
def test_unrecognized_tool_string_is_detected(profile):
    """오타·신종·서술형 문자열은 '정보 없음' 이 아니다 — 판별 불가와는 다르게 잡아야 한다."""
    assert is_unrecognized_tool(profile)


def test_unrecognized_tool_ignores_absent_fields():
    """필드가 아예 없거나 None 이면 '완화' 유지 — 미상(rung 0)일 뿐 unrecognized 는 아니다."""
    assert not is_unrecognized_tool({})
    assert not is_unrecognized_tool({"fetcher_type": None, "antibot_strategy": None})


def test_unrecognized_tool_accepts_known_values():
    assert not is_unrecognized_tool({"fetcher_type": "Fetcher", "antibot_strategy": "none"})
    assert not is_unrecognized_tool({"fetcher_type": "chrome_cdp"})
    assert not is_unrecognized_tool({"antibot_strategy": "authenticated_browser"})


def test_unrecognized_tool_flags_non_string():
    assert is_unrecognized_tool({"fetcher_type": ["chrome_cdp"]})


def test_neutral_values_are_ignored():
    """none/null/빈값은 '전략 없음' 이지 미상이 아니다."""
    assert ladder_rung({"fetcher_type": "Fetcher", "antibot_strategy": "none"}) == 1
    assert ladder_rung({"fetcher_type": "Fetcher", "antibot_strategy": None}) == 1


def test_max_rung_wins():
    assert ladder_rung({"fetcher_type": "Fetcher", "antibot_strategy": "chrome_cdp"}) == 6


@pytest.mark.parametrize("bad", [["chrome_cdp"], {"tool": "chrome_cdp"}, 6, True])
def test_non_string_field_is_not_published(bad):
    """문자열이 아닌 값은 '대응 없음' 이 아니라 '판별 불가' 다 — 배포하지 않는다."""
    assert ladder_rung({"fetcher_type": "Fetcher", "antibot_strategy": bad}) == 0
    assert distribution({"fetcher_type": "Fetcher", "antibot_strategy": bad}) == "local"


def test_authenticated_browser_is_not_auto_published():
    """로그인 기반 수집은 우회가 아니지만 자동 배포 대상도 아니다."""
    assert distribution({"fetcher_type": "Playwright",
                         "antibot_strategy": "authenticated_browser"}) == "local"


def test_withheld_tool_cannot_be_rescued_by_declaration():
    """'알고서 뺀 것' 은 '모르는 것' 과 다르다 — 선언 한 줄로 풀리면 안 된다."""
    assert distribution({"fetcher_type": "Playwright",
                         "antibot_strategy": "authenticated_browser",
                         "distribution": "public"}) == "local"


def test_unknown_tool_can_still_be_rescued():
    """미상은 여전히 구제 가능하다 — 그게 rung 0 과 WITHHELD 의 차이다."""
    assert distribution({"fetcher_type": "SomeInternalHelper",
                         "distribution": "public"}) == "public"


@pytest.mark.parametrize("bad", [["authenticated_browser"], ["chrome_cdp"], {"t": "cdp"}, 4])
def test_non_string_field_cannot_be_rescued_by_declaration(bad):
    """읽을 수 없는 입력을 선언 한 줄로 배포하게 두면, 비문자열 하드닝이 무의미해진다."""
    assert distribution({"fetcher_type": "Playwright", "antibot_strategy": bad,
                         "distribution": "public"}) == "local"


def test_string_unknown_tool_is_still_rescuable():
    """'읽을 수 없음' 과 '읽었지만 모르는 도구' 는 다르다 — 후자는 여전히 구제 가능하다."""
    assert distribution({"fetcher_type": "SomeInternalHelper",
                         "distribution": "public"}) == "public"


# ── 네 술어가 비문자열에 대해 같은 답을 내는가 (호출 순서 비의존) ──
@pytest.mark.parametrize("bad", [["chrome_cdp"], {"t": "cdp"}, 6, True, 0.5])
def test_all_predicates_fail_closed_on_non_string(bad):
    """비문자열의 뜻이 술어마다 달라선 안 된다 — '읽을 수 없음' 하나여야 한다.

    예전에는 `ladder_rung` 만 닫히고(0) `is_withheld_tool` 은 열려서(False), 불변식이
    distribution() 이 `_has_non_string_field` 를 먼저 호출한다는 **순서**로만 유지됐다.
    순서는 리팩터링 한 번이면 바뀐다. 술어 각각이 스스로 닫히는지 직접 건다.
    """
    from profile_policy import _has_non_string_field, is_withheld_tool
    profile = {"fetcher_type": "Fetcher", "antibot_strategy": bad}
    assert ladder_rung(profile) == 0
    assert is_withheld_tool(profile) is True
    assert is_unrecognized_tool(profile) is True
    assert _has_non_string_field(profile) is True


def test_withheld_predicate_alone_blocks_a_non_string():
    """distribution() 이 `_has_non_string_field` 검사를 잃어도 여전히 local 이어야 한다 —
    그게 '순서가 아니라 구조가 불변식을 지킨다' 는 말의 실제 내용이다."""
    from profile_policy import is_withheld_tool
    assert is_withheld_tool({"fetcher_type": "Fetcher", "antibot_strategy": ["chrome_cdp"],
                             "distribution": "public"})


# ── 자리표시자는 '대응 없음' 이 아니라 '적지 않음' 이다 ──
@pytest.mark.parametrize("placeholder", ["-", "N/A", "n/a", "???", "—", "TBD", "?", ""])
def test_placeholder_reads_as_unknown_not_neutral(placeholder):
    """`_norm` 이 구두점을 전부 지우기 때문에 `"-"`·`"???"` 는 빈 문자열이 되고, 예전에는
    빈 문자열이 중립값 집합에 있어 "안티봇 대응이 필요 없었다" 로 읽혔다. `"N/A"` 는 `"na"`
    가 되는데 그 `"na"` 도 중립값에 들어 있었다. 셋 다 정보가 아니라 공백이다 — 공백을
    정보로 읽는 것이 이 모듈이 막으려는 fail-open 그 자체다."""
    profile = {"fetcher_type": "Fetcher", "antibot_strategy": placeholder}
    assert ladder_rung(profile) == 0
    assert is_unrecognized_tool(profile)
    assert distribution(profile) == "local"


@pytest.mark.parametrize("value", ["none", "None", "NULL", "null"])
def test_real_neutral_words_still_mean_no_response(value):
    """반대 방향 — 실제 낱말로 적힌 중립값은 계속 정보로 읽혀야 한다. 자리표시자를 미상으로
    보내면서 이쪽까지 같이 조이면 사다리 A 프로필 전체가 배포에서 빠진다."""
    profile = {"fetcher_type": "Fetcher", "antibot_strategy": value}
    assert ladder_rung(profile) == 1
    assert not is_unrecognized_tool(profile)
    assert distribution(profile) == "public"


# ── distribution ──
def test_ladder_a_is_public():
    assert distribution({"fetcher_type": "FetcherSession"}) == "public"


def test_ladder_b_is_local():
    assert distribution({"fetcher_type": "chrome_cdp"}) == "local"


def test_unknown_is_local_by_default_deny():
    assert distribution({"fetcher_type": "SomeNewBypassTool"}) == "local"


def test_local_declaration_always_wins():
    """조이는 방향은 무조건 인정된다."""
    assert distribution({"fetcher_type": "Fetcher", "distribution": "local"}) == "local"


def test_public_declaration_cannot_overturn_ladder_b():
    """푸는 방향으로는 사다리 B 판정을 뒤집지 못한다."""
    assert distribution({"fetcher_type": "chrome_cdp", "distribution": "public"}) == "local"


def test_public_declaration_can_rescue_unknown_tool():
    """rung 0(미상) 오판은 선언으로 구제할 수 있다 — 이게 푸는 방향의 정당한 용도다."""
    assert distribution({"fetcher_type": "SomeInternalHelper", "distribution": "public"}) == "public"


def test_invalid_declaration_falls_back_to_rule():
    assert distribution({"fetcher_type": "chrome_cdp", "distribution": "maybe"}) == "local"


def test_corrupt_profile_is_withheld(tmp_path, monkeypatch):
    """읽기 실패는 '내용 없음' 이 아니라 '미상' 이다 — load_all 이 실제로 그렇게 만드는가."""
    import profile_policy
    (tmp_path / "broken_com").mkdir()
    (tmp_path / "broken_com" / "profile.json").write_text("{not json", encoding="utf-8")
    (tmp_path / "notobject_com").mkdir()
    (tmp_path / "notobject_com" / "profile.json").write_text("[1, 2]", encoding="utf-8")
    monkeypatch.setattr(profile_policy, "FINGERPRINTS", tmp_path)
    loaded = profile_policy.load_all()
    assert loaded["broken_com"]["fetcher_type"] == profile_policy.UNREADABLE
    assert not profile_policy.is_distributable(loaded["broken_com"])
    assert not profile_policy.is_distributable(loaded["notobject_com"])
    assert profile_policy.public_dirs() == []


def test_ansi_encoded_profile_is_withheld_not_fatal(tmp_path, monkeypatch):
    """읽을 수 없는 인코딩은 public_dirs() 를 무너뜨리지 않고 미상으로 처리돼야 한다."""
    import profile_policy
    (tmp_path / "ansi_com").mkdir()
    (tmp_path / "ansi_com" / "profile.json").write_bytes(
        '{"domain": "a.com", "notes": "한글"}'.encode("cp949"))
    monkeypatch.setattr(profile_policy, "FINGERPRINTS", tmp_path)
    loaded = profile_policy.load_all()
    assert loaded["ansi_com"]["fetcher_type"] == profile_policy.UNREADABLE
    assert profile_policy.public_dirs() == []


def test_empty_profile_is_local():
    """필드가 하나도 없으면 판단 근거가 없다 — default-deny."""
    assert distribution({}) == "local"


# ── 실제 프로필에 대한 회귀 ──
def test_detection_without_response_stays_public():
    """감지 사실과 우회 여부는 다르다 — 무언가 탐지됐어도 평범한 방법으로 끝냈으면 배포한다."""
    assert distribution({"fetcher_type": "FetcherSession", "antibot_strategy": "none"}) == "public"


def test_impersonation_is_a_ladder_b_response():
    """사이트가 평문을 거절해서 지문을 맞춘 것은 탐색이 아니라 돌파다."""
    assert ladder_rung({"fetcher_type": "FetcherSession", "antibot_strategy": "impersonate"}) == 4
    assert distribution({"fetcher_type": "FetcherSession", "antibot_strategy": "impersonate"}) == "local"


def test_session_intercept_stays_public():
    """g2b: SPA 세션 인터셉트는 우회가 아니라 세션 처리다."""
    profiles = load_all()
    assert is_distributable(profiles["g2b_go_kr"])


def test_local_profiles_on_disk_are_not_distributable():
    """이 머신에 있는 **미배포 프로필**이 배포 대상으로 분류되지 않는가.

    예전에는 이름을 하드코딩했다(coupang_com, oliveyoung_co_kr, ...). 그런데 그 파일들은
    바로 이 정책 때문에 repo 에 없다 — gitignore 로 막혀 있고 각자 머신에만 남는다.
    그래서 clean clone 과 CI 에서 KeyError 로 죽었다. 테스트가 "저장소에 없는 파일" 을
    전제하고 있었던 것이다.

    이름 대신 **디스크에 있는데 배포 화이트리스트에 없는 것 전부**를 대상으로 삼는다.
    로컬에서는 실제 미배포 프로필들이 걸리고, CI 에서는 대상이 0개라 공집합이 된다.

    공집합이어도 되는 이유: 위험한 방향은 이 검사가 아니라
    `test_no_tracked_profile_is_withheld` 가 막는다. 그건 git 이 실제로 추적하는 것을 보므로
    어디서든 돈다. 이 검사는 그 거울상 — "추적 안 되는 것들이 정말 추적되면 안 되는 것들이
    맞는가" 를 파일이 있는 곳에서만 확인한다.
    """
    whitelisted = {line.split("/")[1] for line in _whitelist_block()}
    offenders = [
        name for name, profile in load_all().items()
        if name not in whitelisted and is_distributable(profile)
    ]
    assert not offenders, (
        f"화이트리스트 밖인데 배포 대상으로 분류된 프로필: {offenders} — "
        "분류가 틀렸거나 sync_domain_list.py 를 안 돌렸다"
    )


def test_expected_public_count():
    assert public_dirs() == [
        "books_toscrape_com",
        "builtini_co_kr",
        "celimax_co_kr",
        "data_seoul_go_kr",
        "db_itkc_or_kr",
        "g2b_go_kr",
        "guesskorea_com",
        "made-in-china_com",
        "wanted_co_kr",
        "www_11st_co_kr",
        "www_fss_or_kr",
        "www_gsmarena_com",
        "www_k-startup_go_kr",
        "www_kdca_go_kr",
        "www_kurly_com",
    ]


# ── .gitignore default-deny ──
import subprocess

from profile_policy import REPO_ROOT, load_all

GITIGNORE = REPO_ROOT / ".gitignore"
BEGIN = "# BEGIN GENERATED: public-profiles"
END = "# END GENERATED: public-profiles"


def _whitelist_block() -> list[str]:
    text = GITIGNORE.read_text(encoding="utf-8")
    body = text[text.index(BEGIN) + len(BEGIN):text.index(END)]
    return [line.strip() for line in body.splitlines() if line.strip().startswith("!")]


def test_whitelist_block_exists():
    assert BEGIN in GITIGNORE.read_text(encoding="utf-8")


def test_whitelist_matches_classifier():
    """생성 블록이 분류기와 어긋나면 sync 를 돌려야 한다."""
    listed = {line.split("/")[1] for line in _whitelist_block()}
    assert listed == set(public_dirs())


def test_no_blanket_profile_whitelist():
    """default-allow 로 되돌아가지 않았는지 — 이 한 줄이 정책 전체를 무력화한다."""
    for line in GITIGNORE.read_text(encoding="utf-8").splitlines():
        assert line.strip() != "!fingerprints/*/profile.json"
        assert line.strip() != "!fingerprints/*/recipe.md"


def test_credential_blocks_come_after_whitelist():
    """last-match-wins — 자격증명 재차단이 whitelist 뒤에 있어야 한다."""
    lines = [l.strip() for l in GITIGNORE.read_text(encoding="utf-8").splitlines()]
    assert lines.index("**/cookies*.json") > lines.index(END)
    assert lines.index("**/*auth*.json") > lines.index(END)
    assert lines.index("**/*token*.json") > lines.index(END)
    assert lines.index("**/*secret*") > lines.index(END)


def test_new_bypass_profile_cannot_be_staged(tmp_path):
    """default-deny 실증 — 새 우회 프로필은 인덱스 진입 자체가 막혀야 한다."""
    target = REPO_ROOT / "fingerprints" / "zz_policy_probe_com"
    target.mkdir(parents=True, exist_ok=True)
    probe = target / "profile.json"
    probe.write_text('{"domain": "zz-probe.example", "fetcher_type": "chrome_cdp"}',
                     encoding="utf-8")
    try:
        result = subprocess.run(
            ["git", "check-ignore", "-q", str(probe.relative_to(REPO_ROOT))],
            cwd=REPO_ROOT, capture_output=True,
        )
        assert result.returncode == 0, "새 우회 프로필이 gitignore 에 막히지 않습니다"
    finally:
        probe.unlink()
        target.rmdir()


def test_no_tracked_profile_is_withheld():
    """git 이 실제로 추적 중인 fingerprints/ 아래 항목 중에 배포 화이트리스트 밖의 파일이
    섞여 있으면 안 된다.

    다른 테스트들은 '분류기가 옳은가', '화이트리스트가 분류기와 맞는가' 를 본다.
    이건 다른 질문이다 — **이 PR 이 지금 실제로 무엇을 배포하려 하는가.**
    .gitignore 는 untracked 파일에만 작용하므로 `git add -f` 로 강제 추가됐거나 이미
    추적 중인 프로필은 막지 못한다. 그 경우를 잡는 것은 이 검사뿐이다.

    판정은 디렉터리가 아니라 **생성된 배포 화이트리스트**(`.gitignore` 의 `# BEGIN/END
    GENERATED: public-profiles` 블록, `_whitelist_block()`)를 기준으로 한다 — 파일명까지
    화이트리스트에 정확히 있어야 통과한다. 예전 버전(디렉터리 단위 판정)은 `fingerprints/
    wanted_co_kr/recipe.md` 처럼 **이미 공개된 디렉터리 안에 화이트리스트에 없는 새
    파일**(구조 필드 대신 프로즈로 적은 우회 기법)을 놓쳤다 — 디렉터리가 public 이면 그
    안의 무엇이든 통과시켰기 때문이다. 화이트리스트는 `sync_domain_list.py` 가 같은
    분류기로 생성하고 `test_whitelist_matches_classifier` 가 드리프트를 막으므로, 이 판정은
    새로 유지할 게 없다.

    `git ls-files -z`(NUL 구분, `--`로 pathspec 고정)를 쓴다 — 공백 포함 경로와,
    `core.quotePath` 기본값이 8진 이스케이프로 감싸는 비-ASCII 경로(`sanitize_filename` 은
    Unicode-aware 라 `한글.kr` → `한글_kr` 같은 디렉터리가 실제로 생긴다) 양쪽을 한 번에
    깨끗하게 파싱하기 위해서다. pathspec 이 아무것도 못 찾으면(예: fingerprints/ 디렉터리
    자체가 사라지거나 이름이 바뀌면) 이 검사가 조용히 통과해버릴 수 있으므로, 빈 결과는
    그 자체로 실패로 취급한다.

    두 가지는 이 검사의 한계로 남는다.
    - `public_dirs()`(따라서 화이트리스트)는 **디스크 상태**를 읽는다 — 그래서 배포 중이던
      public 프로필을 디스크에서 지우고 그 삭제를 커밋하지 않으면, 진짜 원인은 "삭제가
      스테이징 안 됨"인데 이 테스트는 단순 화이트리스트 불일치로 실패한다. 실패 메시지가
      그 경우의 원인을 정확히 설명하지는 않는다.
    - 로컬 실행은 **인덱스/워킹트리 분기**를 못 잡는다 — 기존 public 프로필의 우회형
      내용을 `git add` 로 스테이징하면서 디스크의 무해한 버전은 그대로 두면, 분류기가
      디스크를 읽으므로 통과해버린다. **CI 는 이 허점이 없다** — checkout 이 인덱스와
      워킹트리를 동일하게 만들므로 커밋된 내용은 항상 이 검사를 거친다. 로컬 실행(예:
      pre-push)에서 그린이 나온 것을 이 지점에 대한 증명으로 오해하면 안 된다.
    """
    raw = subprocess.run(
        ["git", "ls-files", "-z", "--", "fingerprints"],
        cwd=REPO_ROOT, capture_output=True, check=True,
    ).stdout.decode("utf-8")
    listed = [p for p in raw.split("\0") if p]
    assert listed, "git ls-files 가 아무것도 찾지 못했습니다 — 이 검사가 무력화됐습니다"

    allowed = {line[1:] for line in _whitelist_block()}
    offenders = [p for p in listed if p not in allowed]

    assert offenders == [], (
        f"배포 화이트리스트 밖의 파일이 git 에 추적되고 있습니다: {offenders}. "
        "`git rm --cached <경로>` 로 인덱스에서 빼세요 — 파일은 디스크에 그대로 남습니다."
    )
