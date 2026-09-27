"""scripts/continuity_check.py — 계획 연속성 검사기.

각 AI 가 다음 세션에서 무엇을 이어서 해야 하는지 **포인터가 어긋나지 않았는지**를
결정적으로 판정한다. AI 호출도 네트워크도 없다. 그래서 같은 입력이면 언제나 같은 판정이다.

왜 이 파일이 있는가: 이 저장소는 이미 pytest 와 생성물 sync 검사라는 결정론적 검사를
갖추고 있다. 하네스가 더하는 값은 딱 하나다 — **"지금 하고 있는 일"과 "문서에 적힌
계획"이 같은가를 확인하는 것.** 그 대조는 사람이 읽어야만 알 수 있었고, 그래서
매 세션마다 말이 바뀌었다. 여기서는 그걸 파일 대조로 바꾼다.

실패 메시지는 항상 `기대값 / 실제값 / 고칠 파일` 세 가지를 담는다. 이 체커는
제품 파일을 고치지 않��, 우선순위를 정하지 않는다. 판정만 한다.

사용법:
    python scripts/continuity_check.py [--root .]
종료 코드: 0 통과, 1 위반, 2 상태 파일 없음
"""
import argparse
import hashlib
import json
import pathlib
import sys

STAGES = {"RED", "GREEN", "REFACTOR", "VERIFY", "POST_CHECK"}
UNVERIFIED = "UNVERIFIED"


class Report:
    """위반 수집기. 위반이 하나라도 있으면 종료 코드 1."""

    def __init__(self) -> None:
        self.violations: list[str] = []
        self.warnings: list[str] = []

    def fail(self, expected, actual, fix_hint: str) -> None:
        self.violations.append(f"위반: {fix_hint}\n    기대: {expected}\n    실제: {actual}")

    def warn(self, message: str) -> None:
        self.warnings.append(message)

    def emit(self) -> int:
        for message in self.warnings:
            print(f"주의 [UNVERIFIED]: {message}")
        if not self.violations:
            print("연속성 검사 통과 — 포인터와 실제 파일이 일치한다")
            return 0
        print(f"연속성 검사 실패 — {len(self.violations)}건\n")
        for message in self.violations:
            print(message)
        return 1


def _load_json(path: pathlib.Path, label: str, report: Report):
    if not path.exists():
        report.fail(f"{label} 존재", f"{path} 없음", f"{label} 을 만들거나 경로를 고쳐라")
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        report.fail(f"{label} 이 올바른 JSON", f"파싱 실패: {exc}", f"{path} 의 JSON 문법을 고쳐라")
        return None


def _resolve_inside(root: pathlib.Path, rel: str) -> pathlib.Path | None:
    """참조가 저장소 밖으로 나가면 None. symlink 를 따라간 실제 경로로 판정한다."""
    root = root.resolve()
    target = (root / rel).resolve()
    if root == target or root in target.parents:
        return target
    return None


def _need_mapping(value, label, report):
    """dict 를 기대하는 자리에 다른 타입이면 위반 처리하고 None 을 돌려준다.

    이게 없으면 `.get` 이 AttributeError 를 던져 traceback 으로 죽고, 사용자는
    무엇을 고쳐야 하는지 알 수 없다(모듈 docstring 의 약속과 어긋난다).
    """
    if value is None:
        return None
    if not isinstance(value, dict):
        report.fail(
            f"{label} 가 JSON 객체(dict)", f"{type(value).__name__}",
            f"{label} 를 {{... }} 객체로 적어라",
        )
        return None
    return value


def _check_pinned_file(root, rel, expected_sha, label, report) -> None:
    """digest 로 고정된 파일의 존재·경계·내용 일치를 확인한다."""
    if not isinstance(rel, str) or not rel:
        report.fail(f"{label} 의 path 존재", f"{rel!r}", "경로를 문자열로 적어라")
        return
    resolved = _resolve_inside(root, rel)
    if resolved is None:
        report.fail(f"{label} 이 저장소 안", f"{rel} → 저장소 밖을 가리킴", f"{rel} 를 저장소 안 경로로 고쳐라")
        return
    if not resolved.is_file():
        report.fail(
            f"{label} 가 가리키는 대상이 파일", f"{rel} 은/는 파일이 아니다",
            f"{rel} 를 실제 파일로 가리키게 고쳐라",
        )
        return
    if not isinstance(expected_sha, str) or not expected_sha:
        # 핀을 *지운* 것은 미확인이 아니라 핀 해제다. 조용히 통과시키지 않는다.
        report.fail(
            f"{label} sha256 핀 존재", f"{expected_sha!r}",
            "digest 핀을 지우면 승인 없는 변형을 아무도 못 막는다. "
            f"`shasum -a 256 {rel}` 로 실제 해시를 기록하거나, "
            f"아직 모른다면 문자열 'UNVERIFIED' 를 명시하라",
        )
        return
    if expected_sha == UNVERIFIED:
        report.warn(f"{label} sha256 이 {UNVERIFIED} — 확인하지 못했다. 채우려면 `shasum -a 256 {rel}`")
        return
    actual = hashlib.sha256(resolved.read_bytes()).hexdigest()
    if actual != expected_sha:
        report.fail(
            f"{label} sha256 = {expected_sha[:16]}…",
            f"{actual[:16]}… ({rel} 이 바뀜)",
            f"의도한 변경이면 policy 의 sha256 를 갱신하라 — 승인 없는 변형은 조용히 통과하면 안 된다",
        )


def _check_policy(root, policy, report) -> None:
    north_star = _need_mapping(policy.get("north_star"), "policy.north_star", report) or {}
    goal_id = north_star.get("id")
    if not goal_id:
        report.fail("north_star.id 존재", "없음", "policy.json 의 north_star.id 를 채워라")
    elif not north_star.get("statement"):
        report.fail("north_star.statement 존재", "빈 값", "한 문장으로 목적을 적어라")

    work = _need_mapping(policy.get("active_work"), "policy.active_work", report) or {}
    work_id = work.get("id")
    if not work_id:
        report.fail("active_work.id 존재", "없음", "policy.json 의 active_work.id 를 채워라")
        return

    roadmap = work.get("roadmap_id")
    if not roadmap:
        report.fail(
            "active_work.roadmap_id 존재", "없음",
            "활성 작업이 NORTH STAR 에 속하는지 판정할 수 없다",
        )
    elif goal_id and roadmap != goal_id:
        report.fail(
            f"active_work.roadmap_id = {goal_id}", f"{roadmap}",
            "활성 작업이 NORTH STAR 밖이다 — 계획을 바꾸거나 north_star 를 맞춰라",
        )

    contract = work.get("contract_path")
    if not contract:
        report.fail("active_work.contract_path 존재", "없음", "수락 기준이 담긴 계약을 가리키라")
    else:
        resolved = _resolve_inside(root, contract)
        if resolved is None:
            report.fail(
                "active_work.contract_path 가 저장소 안", f"{contract} → 저장소 밖",
                "저장소 안 경로로 고쳐라",
            )
        elif not resolved.exists():
            report.fail(
                "active_work.contract_path 가 가리키는 계약 파일 존재", f"{contract} 없음",
                "active_work.contract_path 의 계약을 만들거나 경로를 고쳐라",
            )

    interrupt = _need_mapping(policy.get("interrupt"), "policy.interrupt", report) or {}
    if interrupt.get("status") == "active":
        if not interrupt.get("exit_criteria"):
            report.fail(
                "활성 interrupt 의 exit_criteria 존재", "빈 목록",
                "인터럽트를 언제 끝내는지 적지 않으면 복귀할 수 없다",
            )
        if not interrupt.get("return_to"):
            report.fail(
                "활성 interrupt 의 return_to 존재", "없음",
                "인터럽트 종료 후 돌아갈 지점을 지금 정해둬라",
            )
    elif policy.get("return_to") != work_id:
        report.fail(
            f"return_to = {work_id} (인터럽트 없음)", f"{policy.get('return_to')}",
            "복귀점이 활성 작업과 다르다 — 어디로 돌아가야 하는지 한 곳에 적어라",
        )

    approval = _need_mapping(policy.get("plan_approval"), "policy.plan_approval", report) or {}
    if not approval.get("path"):
        report.fail("plan_approval.path 존재", "없음", "승인된 계획 파일을 가리키라")
    else:
        _check_pinned_file(
            root, approval.get("path"), approval.get("sha256"),
            f"승인 계획 {approval.get('id', '?')}", report,
        )

    baseline = policy.get("decision_baseline")
    if not isinstance(baseline, list):
        report.fail(
            "decision_baseline 이 JSON 배열", f"{type(baseline).__name__}",
            "결정 베이스라인은 [{...}] 배열이어야 한다",
        )
        return
    if not baseline:
        # 비면 "어느 결정이 적용 중인지"를 알 수 없다. 다음 세션이 그 결정 위에서 일한다.
        report.fail(
            "decision_baseline 에 최소 1건", "빈 배열",
            "적용 중인 결정을 기록해라 — 결정 기록이 없으면 새 세션이 판단 근거를 잃는다",
        )
    for index, entry in enumerate(baseline):
        entry = _need_mapping(entry, f"decision_baseline[{index}]", report)
        if entry is None:
            continue
        rel = entry.get("path")
        if not rel:
            report.fail(
                f"decision_baseline[{index}] 의 path 존재", "없음", "결정 기록 파일을 가리키라",
            )
            continue
        _check_pinned_file(
            root, rel, entry.get("sha256"), f"결정 {entry.get('id', '?')}", report,
        )


def _check_state(root, state, policy, report) -> None:
    work = _need_mapping(policy.get("active_work"), "policy.active_work", report) or {}
    expected_work = work.get("id")
    if state.get("active_work_id") != expected_work:
        report.fail(
            f"state.active_work_id = {expected_work}", f"{state.get('active_work_id')}",
            ".harness/state.json 의 active_work_id 를 policy 와 맞춰라",
        )

    stage = state.get("stage")
    if stage not in STAGES:
        report.fail(
            f"state.stage ∈ {sorted(STAGES)}", f"{stage}",
            "알 수 없는 단계다 — 미정의 단계는 복구 지점을 흐리게 만든다",
        )

    if not isinstance(state.get("dirty"), bool):
        report.fail(
            "state.dirty 가 bool", f"{state.get('dirty')!r} ({type(state.get('dirty')).__name__})",
            "문자열이 아니라 JSON boolean 으로 적어라",
        )


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="계획 연속성 검사기")
    parser.add_argument("--root", default=".", help="저장소 루트 (기본: 현재 디렉터리)")
    args = parser.parse_args(argv)

    root = pathlib.Path(args.root).resolve()
    report = Report()

    policy_path = root / ".harness/policy.json"
    state_path = root / ".harness/state.json"
    if not policy_path.exists() and not state_path.exists():
        print(f"하네스 미설치 — {policy_path} 과 {state_path} 가 모두 없다", file=sys.stderr)
        return 2

    policy = _load_json(policy_path, ".harness/policy.json", report)
    state = _load_json(state_path, ".harness/state.json", report)
    if policy is None or state is None:
        return report.emit()

    # 최상위 자체가 객체가 아닐 수 있다 — `[]` 나 `"문자열"` 도 유효한 JSON 이다.
    if not isinstance(policy, dict) or not isinstance(state, dict):
        report.fail(
            "policy.json / state.json 이 JSON 객체",
            f"policy={type(policy).__name__}, state={type(state).__name__}",
            "두 파일 모두 {{... }} 객체여야 한다",
        )
        return report.emit()

    _check_policy(root, policy, report)
    _check_state(root, state, policy, report)
    return report.emit()


if __name__ == "__main__":
    raise SystemExit(main())
