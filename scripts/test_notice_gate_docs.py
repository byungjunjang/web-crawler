"""통지 게이트 문서 드리프트 — 산문 지시가 조용히 사라지지 않도록.

protego 가 requirements 에 있으면서 어디서도 import 되지 않은 채 몇 달을 보낸 전례가 있다.
문서에만 적힌 규칙은 반드시 흐트러진다.
"""
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SKILL = REPO_ROOT / ".claude/skills/web-crawler/SKILL.md"
CLAUDE_MD = REPO_ROOT / "CLAUDE.md"
CRAWL_REF = REPO_ROOT / "docs/crawl-reference.md"
ANTIBOT = REPO_ROOT / ".claude/skills/web-crawler/references/antibot-strategies.md"
README = REPO_ROOT / "README.md"
ACCEPTABLE_USE = REPO_ROOT / "ACCEPTABLE_USE.md"
AGENTS_MD = REPO_ROOT / "AGENTS.md"

# AGENTS.md 는 Codex 가 실제로 실행하는 계약 문서인데 한동안 어느 드리프트 테스트에도 없었다.
# 그 결과 브랜치 내내 네 번의 문서 정리를 전부 비껴가, 이미 고쳐진 규칙의 옛 판본이 여기서만
# 살아남았다(자동 우회 금지 문구, ToS 위반 = 거절). 지시 문서는 전부 같은 검사를 받는다.
#
# CRAWL_REF 는 2026-10-02 에 CLAUDE.md 를 200줄 미만으로 줄이면서 안전·통지 규칙을
# 원문 그대로 옮긴 곳이다. 규칙의 1차 노출 위치가 CLAUDE.md 에서 이 문서로 이동했다.
GATE_DOCS = [SKILL, CLAUDE_MD, CRAWL_REF, ANTIBOT, AGENTS_MD]


@pytest.mark.parametrize("path", GATE_DOCS, ids=lambda p: p.name)
def test_notice_gate_present(path):
    """이음매 통지가 네 지시 문서에 전부 살아 있어야 한다."""
    text = path.read_text(encoding="utf-8")
    assert "통지" in text, f"{path.name} 에서 통지 게이트 서술이 사라졌습니다"


def test_skill_offers_an_explicit_choice():
    """통지는 알림이 아니라 선택지다 — 사용자가 고를 수 있어야 한다."""
    assert "[진행 / 중단]" in SKILL.read_text(encoding="utf-8")


def test_skill_does_not_demand_justification():
    """원칙 ④ — 근거를 제출받거나 검증하지 않는다."""
    text = SKILL.read_text(encoding="utf-8")
    assert "근거를 묻지도 검증하지도 않는다" in text


@pytest.mark.parametrize("path", GATE_DOCS + [README, ACCEPTABLE_USE], ids=lambda p: p.name)
def test_docs_do_not_overclaim_a_ban(path):
    """문서가 실제 동작보다 강하게 말하면 안 된다 — 통지지 금지가 아니다.

    GATE_DOCS 를 통해 AGENTS.md 도 여기에 들어온다 — 실제로 이 검사가 AGENTS.md 에 남아 있던
    'CAPTCHA 자동 우회 금지' 를 잡았다.
    """
    text = path.read_text(encoding="utf-8")
    for phrase in ("우회하지 않는다", "우회 금지", "우회를 하지 않습니다"):
        assert phrase not in text, (
            f"{path.name} 에 '{phrase}' 가 있습니다. 이 도구는 우회 능력을 유지하며 "
            "사용자가 진행을 고르면 그대로 진행합니다 — 문서가 동작보다 강하게 말하면 안 됩니다"
        )


def test_captcha_rule_is_layered_with_waf():
    """G2 — CAPTCHA 와 WAF 가 같은 층위여야 한다. 자동 풀이 금지는 별개로 유지.

    2026-10-02 — 안전 규칙 절이 `docs/crawl-reference.md` 로 옮겨졌다. 이 문구의 1차
    노출 위치도 그 문서다(CLAUDE.md 는 요약과 링크만 둔다).
    """
    text = CRAWL_REF.read_text(encoding="utf-8")
    assert "CAPTCHA 자동 풀이 금지" in text
    assert "CAPTCHA·WAF·봇 탐지는 법적으로 같은 보호조치" in text


def _section(path: Path, start_heading: str, end_heading: str) -> str:
    """path 에서 start_heading 부터 그 다음 end_heading 직전까지만 잘라 반환한다.

    scripts/test_ladder_docs.py 의 `_fetcher_chain_block()` 관례를 따른다 — 문서 전체가
    아니라 해당 라우팅 절만 봐야, 같은 문구가 다른 절에 살아남아 있다는 이유로 회귀를
    놓치지 않는다. 헤딩이 안 보이면(문서 구조가 바뀌면) 조용히 빈 문자열을 돌려주는 대신
    크게 실패한다 — 검사가 조용히 멈추는 것 자체가 드리프트다.
    """
    text = path.read_text(encoding="utf-8")
    if start_heading not in text:
        raise AssertionError(
            f"{path.name} 에서 '{start_heading}' 섹션을 찾지 못했습니다 — 헤딩이 바뀌었다면 "
            "이 테스트의 앵커도 같이 갱신해야 합니다"
        )
    after_start = text[text.index(start_heading) + len(start_heading):]
    if end_heading not in after_start:
        raise AssertionError(
            f"{path.name} 에서 '{start_heading}' 다음의 '{end_heading}' 를 찾지 못했습니다 — "
            "섹션 순서나 헤딩이 바뀌었다면 이 테스트의 앵커도 같이 갱신해야 합니다"
        )
    return after_start[: after_start.index(end_heading)]


def _absolute_rule_zero_block() -> str:
    """`docs/crawl-reference.md` 의 '★ 절대 규칙 0' 절만 잘라 반환 (다음 '##' 절 직전까지).

    2026-10-02 — 이 절은 CLAUDE.md 에서 crawl-reference.md 로 원문 그대로 옮겼다.
    """
    return _section(
        CRAWL_REF,
        "## ★ 절대 규칙 0: 도메인 히스토리 우선 (모든 수집의 시작)",
        "## 범위 / 운영 안전 규칙",
    )


def _fetcher_decision_tree_section() -> str:
    """`docs/crawl-reference.md` 의 'Fetcher 선택 의사결정 트리' 절 (다음 '##' 절 직전까지).

    2026-10-02 — 이 절은 CLAUDE.md 에서 crawl-reference.md 로 원문 그대로 옮겼다.
    """
    return _section(
        CRAWL_REF,
        "## Fetcher 선택 의사결정 트리",
        "## Spider 활용 기준",
    )


def test_profile_reuse_notice_is_conditional_on_consent():
    """★ 절대 규칙 0 — 프로필이 있다는 사실만으로 통지를 면제하면 안 된다.

    한때 이 파일은 재사용 분기에 무조건 면제를 줬고, 그 문구가 literal `(통지 없음)` 이었다 —
    즉 '통지' 라는 단어를 포함한 채로 게이트가 꺼져 있었다(Task 11 S1). 이 블록은 에이전트가
    수집을 시작할 때 가장 먼저 읽는 라우팅 지시라, "규칙은 문서 어딘가에 살아 있다"로는
    부족하다 — **이 블록 안에서** consent 기록 유무를 조건으로 걸어야 한다. 다른 절(예:
    Fetcher 선택 의사결정 트리)에 같은 문구가 남아 있다는 이유로 이 블록의 회귀를 놓치면 안
    되므로, 문서 전체가 아니라 이 블록만 잘라서 검사한다.
    """
    block = _absolute_rule_zero_block()
    assert "consent 기록이 있나" in block, (
        "★ 절대 규칙 0 블록의 재사용 분기가 consent 기록 유무로 갈라지지 않습니다"
    )
    assert "프로필이 있다는 사실 자체는 게이트를 면제하지 않는다" in block


def test_fetcher_decision_tree_notice_is_conditional_on_consent():
    """Fetcher 선택 의사결정 트리 — Task 11 이 고친 두 번째 구조. 독립적으로 지킨다.

    Step 0(프로필 재사용) 분기가 consent 기록 유무를 조건으로 거는지, ★ 절대 규칙 0 블록과는
    별개로 이 절 자체에서 확인한다. 두 블록은 같은 규칙을 각자의 말로 반복해서 서술하므로,
    한쪽이 통과한다고 다른 쪽의 회귀를 가려서는 안 된다.
    """
    section = _fetcher_decision_tree_section()
    assert "기록이 없으면" in section, (
        "Fetcher 선택 의사결정 트리의 Step 0 분기가 consent 기록 유무를 조건으로 걸지 않습니다"
    )
    assert "이번이 최초 통과" in section


def _antibot_banner_section() -> str:
    """antibot-strategies.md 최상단 배너만 잘라 반환 (목차 직전까지)."""
    return _section(
        ANTIBOT,
        "> ## ■ 이 문서의 우회 티어는 전부 통지 이후에 쓴다 ■",
        "## 목차",
    )


def test_antibot_banner_states_the_notice_rule():
    """antibot-strategies.md — 400줄짜리 문서에 '통지' 라는 단어가 있다는 것만으로는 부족하다.

    이 문서의 절 대부분이 사다리 B 티어라, 게이트 서술이 실제로 걸려 있어야 하는 곳은 문서
    맨 위 배너 하나다. 그 배너가 지워져도 아래 절들 어딘가에 '통지' 라는 단어는 남아 있어
    문서 전체 검사는 그린을 유지한다 — 다른 지시 문서들이 절 단위 앵커를 받은 것과 같은
    이유로 여기도 배너 절만 잘라서 본다.
    """
    banner = _antibot_banner_section()
    assert "사다리 B 에 진입할 때는 자동으로 넘어가지 않고 사용자에게 한 번 알린다" in banner, (
        "antibot-strategies.md 상단 배너에서 사다리 B 진입 통지 규칙이 사라졌습니다"
    )
    assert "근거를 묻지도 검증하지도 않는다" in banner, (
        "배너가 통지를 심사로 만들고 있습니다 — 통지는 근거를 묻지 않습니다"
    )


def _recon_rules_section() -> str:
    """SKILL.md 의 '정찰 규칙' 절만 잘라 반환 (다음 '###' 절 직전까지)."""
    return _section(SKILL, "### 정찰 규칙", "### 정찰 항목")


def _softblock_gate_section() -> str:
    """SKILL.md 의 'Step 5.0: 소프트블록 게이트' 절만 잘라 반환 (다음 '###' 절 직전까지)."""
    return _section(
        SKILL,
        "### Step 5.0: 소프트블록 게이트 (최우선 — 다른 검증보다 먼저)",
        "### 일반 검증",
    )


def test_softblock_returns_to_the_gate():
    """Step 5.0 소프트블록 게이트 — 차단 감지가 이음매를 건너뛰고 직행하면 안 된다.

    Task 10 이 이 파일에서 같은 모양의 경로를 여러 곳 발견했다 — 감지 직후 라우팅을 미리
    확정해 게이트로 돌아가지 않는 형태. 전부 '통지' 라는 단어는 근처에 있었다. 이 문구는
    SKILL.md 안에 이 절 말고도(정찰 규칙 절) 한 번 더 등장하므로, 문서 전체 검사로는 이
    소프트블록 절만 회귀해도 다른 절이 그린을 유지시켜준다 — 이 절 하나로 좁혀서 본다.
    """
    section = _softblock_gate_section()
    assert "이음매 통지 게이트로 돌아간다" in section, (
        "소프트블록 감지 경로가 게이트로 복귀하라고 지시하지 않습니다"
    )


def test_recon_failure_returns_to_the_gate():
    """정찰 규칙 절 — 정찰 단계 실패도 게이트를 거친다. 한때 여기서 바로 CDP 로 갔다.

    같은 이유로 정찰 규칙 절 하나로 좁혀서 본다 — 소프트블록 절에 같은 문구가 남아 있다는
    이유로 이 절의 회귀를 놓치면 안 된다.
    """
    section = _recon_rules_section()
    assert "이음매 통지 게이트로 돌아간다" in section
    assert "정찰 단계에서도 사다리 B 진입은 사용자 확인을 거친다" in section


# ── 법적 위험: 경고하되 판단은 사용자에게 ────────────────────────────────────
#
# 한때 안전 규칙 목록에 "명백히 위법한 요청은 거절" 이 있었다 — 에이전트가 사용자의 법적
# 지위를 스스로 심판하는 규칙인데, 같은 저장소의 ACCEPTABLE_USE.md 는 "저자는 그 판단을 할
# 위치에 있지 않다" 고 이미 말하고 있었다. 그 모순을 없앤 것이 이 검사가 지키는 상태다.
#
# 이 변경은 되돌아오기 쉽다 — '거절' 이 더 안전해 보이기 때문이다. 그래서 두 방향을 함께
# 건다: 위험 범주가 **사라지는 것**(경고할 대상을 잃음)도, 범주 옆에 **거절이 되살아나는
# 것**(심판으로 회귀)도 막는다.
_RISK_CATEGORY_WORDS = ("저작권", "개인정보 대량", "재배포")

_REFUSAL_WORDS = ("거절", "거부", "받지 않", "수행하지 않", "진행하지 않")


def _logical_blocks(section: str) -> list[str]:
    """접혀 있는 목록 항목·문단을 한 덩어리로 되돌린다.

    이 문서들의 규칙 한 줄은 실제로는 여러 줄에 걸쳐 접혀 있다. 줄 단위로 보면 범주 이름과
    거절 문구가 서로 다른 줄에 떨어져 검사를 그냥 통과해버린다 — 실제로 변이 검증에서
    ACCEPTABLE_USE.md 가 그 모양이었다. 빈 줄·목록 마커·헤딩을 경계로 삼아 논리 단위로
    다시 묶는다.
    """
    blocks: list[str] = []
    current: list[str] = []
    for line in section.splitlines():
        boundary = (
            not line.strip()
            or re.match(r"\s*(?:[-*+]|\d+\.)\s", line) is not None
            or line.startswith("#")
        )
        if boundary and current:
            blocks.append(" ".join(current))
            current = []
        if line.strip():
            current.append(line.strip())
    if current:
        blocks.append(" ".join(current))
    return blocks

SAFETY_RULE_SECTIONS = [
    pytest.param(
        README, "## 안전 규칙 (에이전트가 항상 지킴)", "## .gitignore 정책",
        "진행 여부는 사용자가 정합니다", id="README.md",
    ),
    pytest.param(
        CRAWL_REF, "## 범위 / 운영 안전 규칙", "## 핵심 도구",
        "진행 여부는 사용자가 정한다", id="docs/crawl-reference.md",
    ),
    pytest.param(
        AGENTS_MD, "## 안전 — 하드룰 (위반 금지)", "## 빠른 참조",
        "진행 여부는 사용자가 정한다", id="AGENTS.md",
    ),
    pytest.param(
        ACCEPTABLE_USE, "## 이 도구가 하지 않는 일", "## 사용자의 책임",
        "진행 여부는 사용자가 정합니다", id="ACCEPTABLE_USE.md",
    ),
]


@pytest.mark.parametrize("path,start,end,decision_phrase", SAFETY_RULE_SECTIONS)
def test_safety_rules_warn_about_legal_risk_without_refusing(path, start, end, decision_phrase):
    """안전 규칙 절 — 위험 범주는 이름이 남아 있고, 판단은 사용자 몫이어야 한다.

    문서 전체가 아니라 안전 규칙 절만 잘라서 본다 — '거절' 은 이 저장소에서 정당한 다른
    뜻으로도 쓰인다("상대가 나를 식별하고 거절했다"). 문서 전체 검사는 그런 문장에 걸리거나,
    반대로 다른 절이 그린을 유지시켜 이 절의 회귀를 가려버린다.
    """
    section = _section(path, start, end)

    # 되돌아오는 쪽부터 본다 — 진단이 가장 구체적이라 실패 메시지가 바로 원인을 가리킨다.
    for block in _logical_blocks(section):
        matched_refusal = next((w for w in _REFUSAL_WORDS if w in block), None)
        if matched_refusal is None:
            continue
        matched_category = next((w for w in _RISK_CATEGORY_WORDS if w in block), None)
        assert matched_category is None, (
            f"{path.name} 의 안전 규칙 절에서 '{matched_category}' 옆에 '{matched_refusal}' 가 "
            f"돌아왔습니다:\n    {block}\n"
            "에이전트가 사용자의 법적 지위를 스스로 심판하는 규칙입니다 — "
            "ACCEPTABLE_USE.md 의 '사용자의 법적 권한 심사' 조항과 정면으로 어긋납니다. "
            "위험은 알리고, 진행 여부는 사용자가 정합니다"
        )

    # 범주는 **경고 규칙 그 블록 안에** 있어야 한다. 절 어딘가에 있기만 하면 된다고 검사하면
    # README 에서 검사가 헛돈다 — 그 절에는 `재배포` 가 두 번 나오고(경고 bullet 과 무관한
    # 수집 후 이용 bullet), 정작 경고 규칙에서 범주를 지워도 다른 bullet 이 그린을 유지시킨다.
    # 회귀를 막으려고 쓴 테스트가 회귀를 통과시키는 셈이라, 절이 아니라 블록으로 좁힌다.
    warning_block = next(
        (block for block in _logical_blocks(section) if decision_phrase in block), None
    )
    assert warning_block is not None, (
        f"{path.name} 의 안전 규칙 절이 '{decision_phrase}' 라고 말하지 않습니다 — "
        "경고 다음에 오는 것은 심사가 아니라 사용자의 선택입니다"
    )

    for word in _RISK_CATEGORY_WORDS:
        assert word in warning_block, (
            f"{path.name} 의 경고 규칙에서 위험 범주 '{word}' 가 사라졌습니다:\n"
            f"    {warning_block}\n"
            "이 규칙의 값은 요청이 어떤 종류의 위험을 안고 있는지 알려주는 데 있습니다. "
            "범주를 지우면 층위 재배치가 아니라 삭제가 됩니다"
        )


def test_acceptable_use_does_not_speak_for_the_agent():
    """문서가 도구의 동작을 정의하지만, 실행하는 에이전트를 대신 약속하지는 않는다.

    "사용자가 고르면 그대로 진행한다" 는 이 저장소가 지킬 수 없는 약속이다 — 실행 주체는
    자체 판단 기준을 가진 AI 에이전트다. 이 브랜치가 48 개 커밋에 걸쳐 걷어낸 것이 정확히
    그 결함 유형(작동하지 않는 메커니즘을 주장하는 문서)이라, 그 정직성 문구가 조용히
    사라지면 같은 결함이 되돌아온다.
    """
    section = _section(ACCEPTABLE_USE, "## 이 도구가 하는 일", "## 이 도구가 하지 않는 일")
    assert "자체 판단 기준" in section, (
        "ACCEPTABLE_USE.md 상단에서 '실행하는 에이전트는 자체 판단 기준을 갖는다' 는 문구가 "
        "사라졌습니다 — 이 문서가 지킬 수 없는 약속을 하게 됩니다"
    )
    assert "에이전트가 멈추는 경우가 있을 수 있습니다" in section


# ── 통지 재질문 여부: 도메인이 아니라 프로필의 consent 기록 ──────────────────
#
# 356716a 는 "도메인당 1회" 를 "이음매를 통과할 때마다 1회" 로 다섯 곳에서 고쳤지만, 그
# 변경 자체는 리터럴 '도메인당' 검색으로 스윕됐다 — README.md 의 '작동 방식' 절은 같은
# 주장("같은 사이트를 다시 수집할 때는 묻지 않습니다")을 그 낱말 없이 하고 있어서 그
# 스윕에서도, 이 파일의 기존 어떤 테스트에서도 걸리지 않고 살아남았다. 문구가 아니라
# 주장을 검사해야 이런 회귀를 잡는다.


def _readme_operation_summary_section() -> str:
    """README.md 의 '작동 방식 (요약)' 절만 잘라 반환 (다음 '##' 절 직전까지)."""
    return _section(README, "## 작동 방식 (요약)", "## Fingerprint 도메인 별 수집 레시피 기록")


def test_readme_operation_summary_reask_is_keyed_to_consent_not_domain():
    """README.md 작동 방식 절 — 재질문 여부는 도메인이 아니라 프로필의 consent 기록에
    달려 있어야 한다.

    한때 이 절은 "같은 사이트를 다시 수집할 때는 묻지 않습니다" 라고 단정했다 — 도메인
    단위의 once-ever 주장이고, B→A→B 로 돌아온 도메인이 실제로는 재통지된다는 사실과
    어긋난다. 조건화된 새 문구가 살아 있는지, 그리고 옛 단정이 돌아오지 않았는지 둘 다
    확인한다 — 둘 중 하나만 보면 문구만 바뀌고 뜻은 되돌아가는 회귀를 놓친다.
    """
    section = _readme_operation_summary_section()
    assert "그 프로필이 그 기록을 들고 있는 동안은 다시 묻지 않습니다" in section, (
        "README.md 작동 방식 절에서 재질문 조건이 프로필의 consent 기록으로 걸리지 않습니다"
    )
    assert "같은 사이트를 다시 수집할 때는 묻지 않습니다" not in section, (
        "README.md 작동 방식 절이 도메인 단위 once-ever 주장으로 되돌아갔습니다 — "
        "면제 근거는 도메인이 아니라 프로필이 지금 들고 있는 consent 기록입니다"
    )


FREQUENCY_CLAIM_SECTIONS = [
    pytest.param(
        README, "## Fingerprint 도메인 별 수집 레시피 기록 (재수집 가속)", "## 레포 구조",
        "확인이 면제되는 근거는 도메인이 아니라 프로필이 지금 들고 있는 `consent` 기록입니다",
        id="README.md",
    ),
    pytest.param(
        CRAWL_REF, "## ★ 절대 규칙 0: 도메인 히스토리 우선 (모든 수집의 시작)", "## 범위 / 운영 안전 규칙",
        "통지는 도메인당 1회가 아니라 이음매를 통과할 때마다 1회다",
        id="docs/crawl-reference.md",
    ),
    pytest.param(
        AGENTS_MD, "## 안전 — 하드룰 (위반 금지)", "## 빠른 참조",
        "통지를 면제하는 것은 도메인이 아니라 그 프로필이 **지금 들고 있는** `consent` 기록이다",
        id="AGENTS.md",
    ),
    pytest.param(
        SKILL, "### ■ 이음매 — 통지 게이트 ■", "### 사다리 B — 상대가 막고 있다",
        "면제하는 것은 도메인이 아니라 그 프로필이 **지금 들고 있는 `consent` 기록**이다",
        id="SKILL.md",
    ),
]


@pytest.mark.parametrize("path,start,end,phrase", FREQUENCY_CLAIM_SECTIONS)
def test_frequency_claim_is_keyed_to_consent_not_domain(path, start, end, phrase):
    """네 문서 각각의 해당 절에 "재질문 여부는 도메인이 아니라 프로필의 consent 기록에
    달려 있다" 는 진술이 살아 있어야 한다.

    README.md 작동 방식 절은 여기 넣지 않는다 — 그 절은 같은 주장을 이 표의 문서들과
    다른 문구로 하고, 옛 단정의 회귀도 함께 확인해야 하므로 위
    test_readme_operation_summary_reask_is_keyed_to_consent_not_domain 이 따로 다룬다.
    """
    section = _section(path, start, end)
    assert phrase in section, (
        f"{path.name} 의 해당 절에서 '재질문 여부는 도메인이 아니라 프로필의 consent 기록에 "
        "달려 있다' 는 진술이 사라졌습니다"
    )
