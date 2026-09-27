"""연속성 검사기의 계약 테스트 — **얇은 버전**.

다른 프로젝트(`/Users/joonake/Developer/projects/planning-continuity-harness-docs/`)
의 설치 지시서 `PROJECT-HARNESS-INSTALL.md` 4절은 "가장 작은 실용 설치"를
`policy.json` + Task Contract + 검사기 + CI 라고 밝힌다. 여기서는 한 걸음 더 줄여
**판단 근거로 검증할 수 있는 규칙만** 남긴다. 남은 항목과 버린 항목의 이유는
테스트 파일 끝의 "무엇을 왜 버렸나" 에 적었다.

**테스트가 먼저다.** 위반 fixture 가 통과하는 RED 를 확인한 뒤 최소 GREEN 을 만든다.
그리고 통과만 확인하고 실패 재현을 하지 않은 검사는 가드레일이 아니라 장식이다 —
아래 `_assert_violation` 이 그 구분을 강제한다.
"""
import hashlib
import json
import pathlib
import subprocess
import sys

import pytest

REPO = pathlib.Path(__file__).resolve().parent.parent
CHECKER = REPO / "scripts/continuity_check.py"
POLICY = REPO / ".harness/policy.json"
STATE = REPO / ".harness/state.json"

STAGES = {"RED", "GREEN", "REFACTOR", "VERIFY", "POST_CHECK"}


# ── 검사기 실행 헬퍼 ──────────────────────────────────────────────────────

def _run(root: pathlib.Path) -> subprocess.CompletedProcess:
    assert CHECKER.exists(), (
        f"체커 {CHECKER} 가 없다 — 지금의 '위반' 테스트 통과는 판정이 아니라 부재 때문이다"
    )
    return subprocess.run(
        [sys.executable, str(CHECKER), "--root", str(root)],
        capture_output=True, text=True,
    )


def _assert_violation(root: pathlib.Path, needle: str) -> None:
    """위반이 '근거 문자열'과 함께 보고됐는지 확인한다."""
    proc = _run(root)
    combined = proc.stdout + proc.stderr
    assert proc.returncode != 0, f"위반인데 통과했다 (exit=0)\n{combined}"
    assert needle in combined, (
        f"위반은 잡았지만 근거 문자열 {needle!r} 이 없다 — 어떤 규칙이 발화했는지 알 수 없다\n{combined}"
    )


# ── 설치 확인 ────────────────────────────────────────────────────────────

def test_harness_files_exist():
    for p in (POLICY, STATE):
        assert p.exists(), f"{p} 없다 — 하네스 미설치"


def test_real_installed_harness_passes():
    proc = _run(REPO)
    assert proc.returncode == 0, (
        f"설치된 하네스가 자기 검사에 실패했다 (exit={proc.returncode})\n"
        f"{proc.stdout}\n{proc.stderr}"
    )


def test_checker_needs_no_third_party_dependency():
    """표준 라이브러리만 쓴다 — 이 저장소는 requirements.txt 밖에 의존하지 않는다.

    2026-09-27 독립 리뷰 [경] — 줄 시작 `import` 만 긁으므로 `_ = __import__("csv")`
    같은 우회를 통과시켰다. 그래서 줄 기반 스캔과 **실제 import 그래프**를 모두 본다.
    """
    src = CHECKER.read_text(encoding="utf-8")
    allowed = {"json", "sys", "pathlib", "hashlib", "argparse", "os"}

    line_based = {
        line.split()[1].split(".")[0]
        for line in src.splitlines()
        if line.startswith("import ") or line.startswith("from ")
    }
    assert line_based <= allowed, (
        f"체커가 표준 라이브러리 밖을 쓴다: {sorted(line_based - allowed)} — "
        f"이 저장소의 의존성 표면을 키우지 마라"
    )

    # 동적 import 우회: __import__ / importlib 를 코드에서 쓴다
    for dodge in ("__import__", "importlib", "exec(", "eval("):
        assert dodge not in src, (
            f"체커에 `{dodge}` 가 있다 — 의존성 검사를 우회할 수 있다"
        )

    # 실제로 실행해서 import 되는 모듈을 확인한다 (정적 스캔의 한계 보완)
    proc = subprocess.run(
        [sys.executable, "-c",
         "import sys, json, runpy;"
         "before=set(sys.modules);"
         f"runpy.run_path({str(CHECKER)!r}, run_name='not_main');"
         "extra={m.split('.')[0] for m in set(sys.modules)-before"
         " if not m.startswith('_')};"
         "std=set(sys.stdlib_module_names);"
         "print(json.dumps(sorted(extra-std)))"],
        capture_output=True, text=True,
    )
    assert proc.returncode == 0, f"체커 import 검사 실패:\n{proc.stderr}"
    non_stdlib = json.loads(proc.stdout.strip().splitlines()[-1])
    assert not non_stdlib, f"체커가 표준 라이브러리 밖 모듈을 불러온다: {non_stdlib}"


# ── 픽스처 ───────────────────────────────────────────────────────────────

def _sha256(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture()
def harness(tmp_path: pathlib.Path) -> pathlib.Path:
    root = tmp_path / "repo"
    (root / ".harness").mkdir(parents=True)
    (root / "docs/decisions").mkdir(parents=True)
    (root / "docs/plan-approvals").mkdir(parents=True)
    (root / "docs/task-contracts").mkdir(parents=True)

    approval = root / "docs/plan-approvals/GOAL-REV-001.md"
    approval.write_text("# 승인된 계획 REV-001\n", encoding="utf-8")
    adr = root / "docs/decisions/ADR-001.md"
    adr.write_text("# ADR-001\n결정: 채택\n", encoding="utf-8")
    contract = root / "docs/task-contracts/WORK-001.md"
    contract.write_text("# WORK-001 계약\n", encoding="utf-8")

    (root / ".harness/policy.json").write_text(json.dumps({
        "schema_version": "1.0",
        "north_star": {"id": "GOAL-001", "statement": "테스트가 무조건 통과한다"},
        "active_work": {
            "id": "WORK-001",
            "contract_path": "docs/task-contracts/WORK-001.md",
            "roadmap_id": "GOAL-001",
        },
        "return_to": "WORK-001",
        "interrupt": {"status": "none", "return_to": "WORK-001", "exit_criteria": []},
        "plan_approval": {
            "id": "GOAL-REV-001",
            "revision": 1,
            "path": "docs/plan-approvals/GOAL-REV-001.md",
            "sha256": _sha256(approval),
        },
        "decision_baseline": [
            {"id": "ADR-001", "path": "docs/decisions/ADR-001.md", "sha256": _sha256(adr)}
        ],
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    (root / ".harness/state.json").write_text(json.dumps({
        # 기본 픽스처는 **진행 중**이다. dirty=false 는 "세션을 닫았다" 는 선언이라
        # 독립 리뷰 기록 **그리고** 핸드오프 문서를 요구하는데, 정상 상태 픽스처에서
        # 그걸 요구하면 안 된다. 세션 종료 규칙은 아래 테스트들이 명시적으로 만든다.
        "schema_version": "1.0",
        "active_work_id": "WORK-001",
        "stage": "GREEN",
        "dirty": True,
        "verified_commit": None,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    # 닫힌 세션을 다루는 테스트들이 쓸 핸드오프. 없으면 '핸드오프 없음' 이 추가
    # 위반으로 잡혀서, 그 테스트가 보려는 규칙을 가리지 못한다.
    (root / "docs").mkdir(parents=True, exist_ok=True)
    (root / "docs/session-handoff.md").write_text(
        "# 세션 핸드오프\n\n픽스처용 본문.\n", encoding="utf-8")
    return root


def _edit(root: pathlib.Path, rel: str, mutate) -> None:
    p = root / rel
    data = json.loads(p.read_text(encoding="utf-8"))
    mutate(data)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


# ── 검사 규칙: 위반 fixture 는 반드시 0 아닌 exit + 근거 문자열 ──────────

def test_baseline_fixture_passes(harness):
    proc = _run(harness)
    assert proc.returncode == 0, f"정상 상태인데 실패했다:\n{proc.stdout}\n{proc.stderr}"


def test_state_work_must_match_policy(harness):
    _edit(harness, ".harness/state.json",
          lambda d: d.__setitem__("active_work_id", "WORK-999"))
    _assert_violation(harness, "active_work_id")


def test_state_stage_must_be_known(harness):
    _edit(harness, ".harness/state.json", lambda d: d.__setitem__("stage", "MADE-UP"))
    _assert_violation(harness, "stage")


def test_state_dirty_must_be_bool(harness):
    _edit(harness, ".harness/state.json", lambda d: d.__setitem__("dirty", "yes"))
    _assert_violation(harness, "dirty")


def test_active_work_must_carry_roadmap_id(harness):
    """활성 작업이 NORTH STAR 에 속하는지 알 수 있어야 한다."""
    _edit(harness, ".harness/policy.json",
          lambda d: d["active_work"].pop("roadmap_id"))
    _assert_violation(harness, "roadmap_id")


def test_active_work_must_not_point_at_other_goal(harness):
    _edit(harness, ".harness/policy.json",
          lambda d: d["active_work"].__setitem__("roadmap_id", "GOAL-999"))
    _assert_violation(harness, "roadmap_id")


def test_return_to_must_equal_active_work_when_idle(harness):
    _edit(harness, ".harness/policy.json",
          lambda d: d.__setitem__("return_to", "SOMETHING-ELSE"))
    _assert_violation(harness, "return_to")


def test_plan_approval_digest_drift_fails(harness):
    """승인 파일이 바뀌었는데 digest 가 갱신 안 됐으면 실패 — 조용한 계획 변형 방지."""
    (harness / "docs/plan-approvals/GOAL-REV-001.md").write_text("# 몰래 고침\n", encoding="utf-8")
    _assert_violation(harness, "sha256")


def test_decision_digest_drift_fails(harness):
    (harness / "docs/decisions/ADR-001.md").write_text("# 몰래 고침\n", encoding="utf-8")
    _assert_violation(harness, "sha256")


def test_active_work_contract_must_exist(harness):
    (harness / "docs/task-contracts/WORK-001.md").unlink()
    _assert_violation(harness, "contract_path")


def test_active_interrupt_needs_exit_criteria_and_return_point(harness):
    """인터럽트를 열었는데 복귀점이나 종료 조건이 없으면 실패한다."""
    _edit(harness, ".harness/policy.json", lambda d: d.__setitem__("interrupt", {
        "status": "active", "return_to": None, "exit_criteria": [],
    }))
    _assert_violation(harness, "interrupt")


def test_reference_escaping_repo_fails(harness):
    """참조가 저장소 밖을 가리키면 실패한다 — symlink 포함."""
    outside = harness.parent / "outside-plan.md"
    outside.write_text("# 밖의 계획\n", encoding="utf-8")
    link = harness / "docs/plan-approvals/GOAL-REV-001.md"
    link.unlink()
    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip("이 파일시스템에서 symlink 생성 불가")
    _assert_violation(harness, "저장소 밖")


def test_explicit_unverified_is_allowed_but_loud(harness):
    """UNVERIFIED 를 명시하면 통과하되 조용히 흐르면 안 된다.

    값을 지어내지 말라는 규약인데, 조용히 통과하면 그 규약이 사라진다.
    """
    _edit(harness, ".harness/policy.json",
          lambda d: d["plan_approval"].__setitem__("sha256", "UNVERIFIED"))
    proc = _run(harness)
    combined = proc.stdout + proc.stderr
    assert proc.returncode == 0, f"명시적 UNVERIFIED 는 통과해야 한다 (아직 미확인이라는 뜻)\n{combined}"
    assert "UNVERIFIED" in combined, "UNVERIFIED 가 조용히 통과했다 — 무엇이 미확인인지 안 보인다"


def test_missing_digest_key_is_a_violation_not_a_warning(harness):
    """digest 키가 **없으면** 위반이다. 명시적 UNVERIFIED 와 다르다.

    2026-09-27 독립 리뷰 [중] — `entry.get("sha256", UNVERIFIED)` 가 키 부재와 명시적
    "UNVERIFIED" 를 같은 경로로 보내, 필수 핀을 *삭제*해도 경고만 찍고 exit 0 이 됐다.
    핀을 지우는 것은 미확인이 아니라 핀 해제다. 조용히 통과하면 안 된다.
    """
    _edit(harness, ".harness/policy.json",
          lambda d: d["plan_approval"].pop("sha256"))
    _assert_violation(harness, "sha256")


def test_empty_decision_baseline_is_a_violation(harness):
    """결정 베이스라인이 비면 위반이다 — 어느 결정이 적용 중인지 알 수 없으면
    다음 세션이 그 결정 위에서 일한다."""
    _edit(harness, ".harness/policy.json", lambda d: d.__setitem__("decision_baseline", []))
    _assert_violation(harness, "decision_baseline")


@pytest.mark.parametrize("field", ["plan_approval", "decision_baseline"])
def test_malformed_types_report_violation_not_traceback(harness, field):
    """타입이 뒤섞여도 traceback 이 아니라 위반으로 보고한다.

    검사기 모듈 docstring 이 "실패 메시지는 항상 기대/실제/고칠 파일" 이라고 약속한다.
    traceback 으로 죽으면 사용자가 무엇을 고쳐야 하는지 알 수 없다.
    """
    def mutate(d):
        if field == "plan_approval":
            d["plan_approval"] = "문자열"
        else:
            d["decision_baseline"] = "문자열"
    _edit(harness, ".harness/policy.json", mutate)
    proc = _run(harness)
    combined = proc.stdout + proc.stderr
    assert "Traceback" not in combined, f"traceback 으로 죽었다:\n{combined}"
    assert proc.returncode == 1, f"위반인데 종료 코드가 1 이 아니다 (exit={proc.returncode})\n{combined}"


def test_policy_or_state_being_non_object_is_a_violation(harness):
    """policy.json / state.json 이 객체가 아니어도 위반이다."""
    for rel in (".harness/policy.json", ".harness/state.json"):
        (harness / rel).write_text("[]", encoding="utf-8")
        proc = _run(harness)
        combined = proc.stdout + proc.stderr
        assert "Traceback" not in combined, f"{rel} 이 리스트일 때 traceback:\n{combined}"
        assert proc.returncode == 1, f"{rel} 이 리스트인데 통과했다"


def test_missing_policy_fails(tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    proc = subprocess.run(
        [sys.executable, str(CHECKER), "--root", str(empty)],
        capture_output=True, text=True,
    )
    assert proc.returncode != 0
    assert CHECKER.exists()


def test_clean_session_requires_independent_review_record(harness):
    """`dirty: false` = 이 세션을 깨끗이 닫았다고 선언한 것이다.

    그러면 반드시 **독립 리뷰가 돌았다는 기록**이 있어야 한다. 산문 규칙은 안 지키면
    조용히 넘어가므로 검사기로 강제한다 — 2026-09-27 사용자가 세션 종료마다
    독립 리뷰 실행을 요구했다.
    """
    _edit(harness, ".harness/state.json", lambda d: d.__setitem__("dirty", False))
    _assert_violation(harness, "independent_review")


def test_clean_session_with_review_passed_is_accepted(harness):
    """리뷰가 돌았고 findings_open 이 아니면 통과한다."""
    def mutate(d):
        d["dirty"] = False
        d["session_end"] = {"independent_review": {
            "status": "passed", "model": "opencode-go/deepseek-v4.1-flash",
        }}
    _edit(harness, ".harness/state.json", mutate)
    proc = _run(harness)
    assert proc.returncode == 0, f"리뷰 기록이 있는데 실패했다:\n{proc.stdout}\n{proc.stderr}"


def test_clean_session_with_open_findings_is_a_violation(harness):
    """리뷰가 돌았어도 미해결 finding 이 남으면 세션을 닫을 수 없다."""
    def mutate(d):
        d["dirty"] = False
        d["session_end"] = {"independent_review": {
            "status": "findings_open", "model": "x",
        }}
    _edit(harness, ".harness/state.json", mutate)
    _assert_violation(harness, "findings_open")


def test_dirty_session_does_not_require_review_yet(harness):
    """아직 진행 중이면 리뷰 기록을 요구하지 않는다 — 매 단계마다 리뷰는 과하다."""
    def mutate(d):
        d["dirty"] = True
        d.pop("session_end", None)
    _edit(harness, ".harness/state.json", mutate)
    proc = _run(harness)
    assert proc.returncode == 0, f"진행 중인데 리뷰를 요구했다:\n{proc.stdout}\n{proc.stderr}"


def test_review_record_without_model_is_a_violation(harness):
    """어느 모델로 돌렸는지 없으면 재현할 수 없다."""
    def mutate(d):
        d["dirty"] = False
        d["session_end"] = {"independent_review": {"status": "passed"}}
    _edit(harness, ".harness/state.json", mutate)
    _assert_violation(harness, "model")


# 2026-09-27 독립 리뷰가 찾은 우회 3건. 전부 조용히 통과했다.

def test_empty_session_end_object_is_a_violation(harness):
    """`session_end: {}` 로 규칙을 꺼버릴 수 있었다.

    필수 항목의 "부재"를 선택 항목과 같은 경로(`report.fail` 없이 return)로 보내면
    빈 객체 한 번으로 세션 종료 규칙이 통째로 비활성화된다.
    """
    def mutate(d):
        d["dirty"] = False
        d["session_end"] = {}
    _edit(harness, ".harness/state.json", mutate)
    _assert_violation(harness, "independent_review")


def test_null_independent_review_is_a_violation(harness):
    def mutate(d):
        d["dirty"] = False
        d["session_end"] = {"independent_review": None}
    _edit(harness, ".harness/state.json", mutate)
    _assert_violation(harness, "independent_review")


def test_unknown_review_status_is_a_violation_not_a_warning(harness):
    """'done' 같은 임의 값이 경고만 찍고 통과했다 — 'passed' 와 오타나기 쉽다."""
    def mutate(d):
        d["dirty"] = False
        d["session_end"] = {"independent_review": {"status": "done", "model": "m"}}
    _edit(harness, ".harness/state.json", mutate)
    _assert_violation(harness, "status")


def test_whitespace_only_model_is_a_violation(harness):
    def mutate(d):
        d["dirty"] = False
        d["session_end"] = {"independent_review": {"status": "passed", "model": "   "}}
    _edit(harness, ".harness/state.json", mutate)
    _assert_violation(harness, "model")


# ── 무엇을 왜 버렸나 ────────────────────────────────────────────────────
# 원본 지시서의 항목 중 여기 없는 것, 그리고 이유. 버린 항목은 실측 기준으로 결정했다.
#
# · work-items.json  — policy.active_work 가 이미 id·roadmap_id·contract_path 를 갖고
#   있어서 파생 복사본은 드리프트만 늘린다. 지시서 5절도 "파생값을 독립적으로 고쳐
#   새 계획으로 만들면 안 된다" 고 경고하는데, 복제본이 없으면 그 위험 자체가 사라진다.
# · docs/handoff.md  — 세션 상태는 state.json 이 정본이다. 사람이 읽는 인계서는
#   같은 정보를 두 곳에 적으므로 반드시 어긋난다. 세션 재개는 state.json 만 읽으면 된다.
# · evidence manifest — "실제로 실행됐는지는 체커가 증명 못 한다" 고 지시서 5절이
#   인정한다. 증명 못 하는 규칙은 조용히 통과하는 장식이라 두지 않았다.
# · pre-commit 훅   — 지시서 8절이 "선택 사항" 이라 명시. CI 가 최종 검사고,
#   로컬 훅은 커밋을 느리게 만들어 되돌리기 비용을 높인다.
# · handoff_references — handoff 파일이 없으므로 해당 규칙도 필요 없다.
