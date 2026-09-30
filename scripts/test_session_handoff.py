"""세션 종료 핸드오프 문서 하네스의 계약 테스트.

## 왜 있는가 (2026-09-27 실측)

경량 하네스를 설치할 때 `docs/handoff.md` 를 **제가 제외를 결정**했다. 정본이
`.harness/state.json` 하나면 인계서가 드리프트한다는 근거는 타당했다. 하지만
결과적으로 사람이 읽는 종료 문서가 0건이 되었고, 사용자가 그걸 바로 짚었다.

더 나쁜 것은 **문서가 없는데도 세션이 종료됐다고 보고된 것**이었다.
`state.json` 에 `dirty:false` 가 찍히면 "정리됐다" 고 보이지만, 다음 사람이
읽을 수 있는 것은 상태 파일뿐이었다.

## 어떻게 고쳤나

projects 전역 32개를 조사한 결과 지배적 관례를 찾았다 (docs/CONTEXT.md 19개,
`.context/STATE` 18개, `docs/next-session-prompt.md` 18개). 그중 `docstudio` 가
이미 문제를 풀고 있었다 — "모델 비의존 문서 하네스(agent-docs init/check)".

그 해답의 핵심은 **생성 + 드리프트 검사** 다. 사람이 문서를 쓰면 어긋나지만,
정본에서 생성하면 어긋날 수 없다. `docstudio` 는 12개 파일(6개 × 2 위치)을 쓰지만
그건 과하다 — 여기서는 **생성 문서 1개**로 같은 보장을 얻는다.

## 이 파일이 지키는 것

- 세션이 종료됐다면 핸드오프 문서가 **존재**한다
- 그 문서는 `.harness/state.json` 에서 **생성**되므로 어긋나지 않는다
- 문서에 **실측 검증 결과**가 있다 (다음 사람이 믿을 근거)
- 다음 세션이 바로 시작할 **baseline 명령**이 있다
- 어느 **모델**이 일했는지가 기록된다 (재현성)
"""
import hashlib
import json
import pathlib
import re
import subprocess
import sys

REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

import session_handoff as sh  # noqa: E402
from continuity_check import main as checker_main  # noqa: E402

STATE = REPO / ".harness/state.json"
HANDOFF = REPO / "docs/session-handoff.md"
VERIFICATION_BASELINE_COMMAND = sh.VERIFICATION_COMMANDS[0][1]


# ── 1) 파일이 실제로 만들어진다 ─────────────────────────────────────────

def test_module_uses_only_standard_library():
    src = (REPO / "scripts/session_handoff.py").read_text(encoding="utf-8")
    allowed = {"json", "sys", "pathlib", "hashlib", "argparse", "subprocess", "os",
               "datetime", "re", "shlex"}
    line_based = {
        line.split()[1].split(".")[0]
        for line in src.splitlines()
        if line.startswith("import ") or line.startswith("from ")
    }
    assert line_based <= allowed, (
        f"표준 라이브러리 밖을 쓴다: {sorted(line_based - allowed)} — "
        f"이 저장소의 의존성 표면을 키우지 마라"
    )


def test_generated_handoff_exists_and_is_not_empty():
    assert HANDOFF.exists(), (
        f"{HANDOFF} 없다 — `python scripts/session_handoff.py write` 로 생성하라"
    )
    assert HANDOFF.read_text(encoding="utf-8").strip(), "핸드오프 문서가 비어 있다"


# ── 2) 생성본이 정본(state.json)과 어긋나지 않는다 ──────────────────────

def test_check_passes_against_committed_handoff():
    proc = subprocess.run(
        [sys.executable, str(REPO / "scripts/session_handoff.py"), "--check"],
        capture_output=True, text=True, cwd=REPO,
    )
    assert proc.returncode == 0, (
        f"핸드오프가 state.json 과 어긋난다 — 재생성하라\n{proc.stdout}\n{proc.stderr}"
    )


def test_check_detects_staleness(tmp_path, monkeypatch):
    """state.json 을 바꿨는데 핸드오프가 안 바뀌면 잡아야 한다 — 이게 핵심 가치다."""
    state = json.loads(STATE.read_text(encoding="utf-8"))
    original_state = STATE.read_text(encoding="utf-8")
    original_handoff = HANDOFF.read_text(encoding="utf-8")
    try:
        state["active_work_id"] = "SOME-OTHER-WORK"
        STATE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        proc = subprocess.run(
            [sys.executable, str(REPO / "scripts/session_handoff.py"), "--check"],
            capture_output=True, text=True, cwd=REPO,
        )
        assert proc.returncode != 0, (
            "state.json 이 바뀌었는데 핸드오프를 최신으로 판단했다 — 드리프트를 못 잡는다"
        )
    finally:
        STATE.write_text(original_state, encoding="utf-8")
        HANDOFF.write_text(original_handoff, encoding="utf-8")


# ── 3) 문서가 '읽을 만한' 내용인지 ───────────────────────────────────────

def test_handoff_contains_the_essentials():
    text = HANDOFF.read_text(encoding="utf-8")
    requirements = {
        "실측 검증 결과": r"##\s*실측 검증",
        "baseline 명령": r"baseline",
        "작업 도구(모델)": r"작업 도구",
        "남은 것": r"##\s*남은 것",
        "다음 세션 즉시 시작": r"다음 세션",
    }
    missing = [k for k, pat in requirements.items() if not re.search(pat, text)]
    assert not missing, f"핸드오프에 없는 절: {missing}"


def test_handoff_quotes_actual_command_results():
    """baseline 은 '기대값'이 아니라 이 저장소에서 실측한 값이어야 한다.

    docstudio 의 session-close.mjs 도 `baseline` 섹션을 요구한다. 같은 보장이다.
    """
    text = HANDOFF.read_text(encoding="utf-8")
    m = re.search(r"##\s*실측 검증(.*?)(?=\n##\s|\Z)", text, re.S)
    assert m, "실측 검증 절이 없다"
    section = m.group(1)
    assert re.search(r"\d+ passed", section), (
        "실측 검증 절에 통과한 테스트 수가 없다 — 다음 사람이 재현할 근거가 없다"
    )
    assert re.search(r"exit\s*=\s*0|exit 0", section), (
        "실측 검증 절에 exit code 가 없다"
    )


def test_measurement_free_pass_still_satisfies_the_document_contract(tmp_path):
    """**1패스 산출물에도** 실측 수치가 있어야 한다.

    2026-10-01 실측 재현 (2패스 수정이 절반만 고친 상태):
        `write` 직후 문서  = `exit=1 ❌ — 1 failed, 576 passed`
        즉시 실제 baseline = `577 passed`
    즉 `write` 가 **거짓 실패**를 문서에 박았다. 순환은 이렇다 — 1패스가
    `"(실측 안 함)"` 으로 디스크 문서를 덮어쓰고, 2패스가 그 상태에서 pytest 를
    돌리면 `test_handoff_quotes_actual_command_results` 가 그 자리에서 실패하고,
    그 실패가 문서에 `exit=1` 로 기록된다. 다음 `write` 는 또 같은 자리에서 실패한다.

1패스의 본문은 최종 문서와 **같아야 한다**(다이제스트만 갱신되는 것).
    그래서 1패스도 이전 실측 표를 살려 실측 수치를 남겨야 하고,
    그러면 2패스 실측 중 pytest 는 자기참조에서 실패하지 않는다.

    ⚠ `tmp_path` 에 이전 문서를 직접 만들어 준다 (2026-10-01 독립 리뷰 [High]).
    실제 `REPO` 문서를 읽으면 이 테스트가 **디스크 상태**를 재는 것이라
    로직이 아니라 그날의 파일을 판정하게 된다 — 이전 표가 거짓이어도 통과한다.
    여기서는 "이전 표가 있으면 1패스가 그 표를 살린다" 는 규칙만 고정한다.
    """
    root = tmp_path / "repo"
    (root / ".harness").mkdir(parents=True)
    (root / ".harness/state.json").write_text(
        STATE.read_text(encoding="utf-8"), encoding="utf-8")
    (root / ".harness/policy.json").write_text(
        (REPO / ".harness/policy.json").read_text(encoding="utf-8"), encoding="utf-8")
    (root / "docs").mkdir()
    (root / sh.HANDOFF_REL).write_text(
        "| baseline | `python -m pytest -q -k \"not e2e\"` | exit=0 ✅ — 578 passed, 14 deselected |\n",
        encoding="utf-8")

    text = sh.render(root, run_verification=False)
    m = re.search(r"##\s*실측 검증(.*?)(?=\n##\s|\Z)", text, re.S)
    assert m, "1패스 산출물에 실측 검증 절이 없다"
    section = m.group(1)
    assert re.search(r"\d+ passed", section), (
        "1패스 산출물의 실측 표에 통과한 테스트 수가 없다 — 이 문서가 디스크에 놓인 "
        "사이 2패스가 pytest 를 돌리면 그 자리에서 실패해 거짓 수치가 기록된다"
    )
    assert re.search(r"exit\s*=\s*0|exit 0", section), (
        "1패스 산출물의 실측 표에 exit code 가 없다 (같은 이유)"
    )
    assert "578 passed" in section, (
        "1패스가 이전 문서의 실측 값을 **그대로 인용**해야 한다 — 실측을 다시 "
        "돌리지도 않고 지어내지도 않는다"
    )


def test_first_pass_labels_carried_rows_as_previous_run(tmp_path):
    """인용한 행에 **이전 실행값**임을 표시한다 (2026-10-01 독립 리뷰 [High]).

    표시가 없으면 1패스 산출물이 "측정 시점 HEAD: `<현재>`" 아래에
    더 오래된 통과 수를 지금 측정한 것처럼 놓는다. 사람이 중간 산출물을 읽을
    때 오독된다. `run_verification=True` 는 실시간 값이라 표시가 불필요하다.
    """
    root = tmp_path / "repo"
    (root / ".harness").mkdir(parents=True)
    (root / ".harness/state.json").write_text(
        STATE.read_text(encoding="utf-8"), encoding="utf-8")
    (root / ".harness/policy.json").write_text(
        (REPO / ".harness/policy.json").read_text(encoding="utf-8"), encoding="utf-8")
    (root / "docs").mkdir()
    (root / sh.HANDOFF_REL).write_text(
        "| baseline | `python -m pytest -q -k \"not e2e\"` | exit=0 ✅ — 578 passed, 14 deselected |\n",
        encoding="utf-8")

    carried = sh.render(root, run_verification=False)
    section = re.search(r"##\s*실측 검증(.*?)(?=\n##\s|\Z)", carried, re.S).group(1)
    baseline_row = next(l for l in section.splitlines() if l.startswith("| baseline"))
    assert "이전 실행" in baseline_row, (
        f"인용한 행에 출처 표시가 없다: {baseline_row!r} — 사람이 읽으면 "
        "이전 실행의 통과 수를 지금 측정한 것으로 오독한다"
    )
    # 현재 명령 문자열로 재구성했는지도 본다 — 명령이 바뀌면 옛 문자열을 되살리면 안 된다.
    assert VERIFICATION_BASELINE_COMMAND in baseline_row, (
        "명령 칸은 현재 계약의 문자열이어야 한다 — 이전 행을 통째로 복사하면 "
        "옛 명령을 표시한다"
    )
    assert re.search(r"exit\s*=\s*0|exit 0", section), (
        "1패스 산출물의 실측 표에 exit code 가 없다 (같은 이유)"
    )


def test_write_renders_measurement_free_pass_first(tmp_path, monkeypatch):
    """`write` 는 실측 없는 패스를 **먼저** 한 번 돌려야 한다.

    2026-09-28 독립 리뷰 finding(Medium): 1패스로만 쓰면 실측 중 디스크의 옛
    핸드오프 때문에 자기참조 검사 2건이 실패하고, 문서에 `exit=1 ❌ — 2 failed`
    가 참이 아닌 값으로 박힌다(실측: 576 passed / exit=0 인데 exit=1 로 기록됨).
    `--check` 는 다이제스트만 비교하므로 그 거짓을 못 잡는다.

    `render` 를 **-stub** 으로 갈아끼운다. 진짜 render 는 baseline 으로 pytest 를
    돌리는데, 그 안에서 이 테스트가 다시 `write` 를 부르면
    pytest → write → render → pytest 로 무한 재귀한다(모듈 docstring 의 경고).
    그래서 순서만 관찰하고 실측은 하지 않는다.
    """
    root = tmp_path / "repo"
    (root / ".harness").mkdir(parents=True)
    (root / ".harness/state.json").write_text(
        (REPO / ".harness/state.json").read_text(encoding="utf-8"), encoding="utf-8")

    calls = []
    monkeypatch.setattr(
        sh, "render",
        lambda r, run_verification: (calls.append(run_verification), "stub")[1],
    )
    sh.write(root)

    assert calls == [False, True], (
        f"render 호출 순서가 {calls} 이다 — 첫 패스는 실측 없이(=False) 가야 "
        "자기참조가 풀린 상태에서 두 번째 실측이 돌아간다"
    )
    assert (root / sh.HANDOFF_REL).read_text(encoding="utf-8") == "stub", (
        "두 번째 패스(실측 포함)의 결과가 최종 파일이어야 한다"
    )


def test_handoff_states_measurement_provenance():
    """실측 수치 옆에 **어디서** 잰 건지 적는다.

    2026-09-28 독립 리뷰 finding: `write` 는 커밋 전에 불리므로 문서에 찍히는
    커밋 해시는 이 문서를 담는 커밋의 *부모*다. 그 해시만 나란히 적으면
    "그 커밋에서 575 개가 통과했다" 고 읽히지만 실제로는 커밋 *직전* 트리의 수치다.
    출처를 명시하지 않으면 다음 사람이 그 커밋을 재현하다 다른 수를 보고
    드리프트로 오인한다.
    """
    text = HANDOFF.read_text(encoding="utf-8")
    m = re.search(r"##\s*실측 검증(.*?)(?=\n##\s|\Z)", text, re.S)
    assert m, "실측 검증 절이 없다"
    section = m.group(1)
    assert re.search(r"작업 트리|직전", section), (
        "실측 검증 절에 수치가 잰 대상(작업 트리 / 커밋 직전)이 없다 — "
        "커밋 해시만 보이면 그 커밋에서 잰 것처럼 읽힌다"
    )


def test_handoff_names_the_model_that_did_the_work():
    """어느 모델이 일했는지가 재현성의 최소 단위다."""
    state = json.loads(STATE.read_text(encoding="utf-8"))
    review = (state.get("session_end") or {}).get("independent_review") or {}
    model = review.get("model")
    if not model:
        return  # 아직 리뷰 기록이 없으면 이 검사는 대상이 아니다
    assert model in HANDOFF.read_text(encoding="utf-8"), (
        f"핸드오프에 작업 모델({model}) 이 없다 — 리뷰를 재현할 수 없다"
    )


# ── 4) 검사기가 세션 종료에 핸드오프를 요구한다 ─────────────────────────

def test_continuity_check_requires_handoff_when_session_closed(tmp_path):
    """`dirty: false` 면 핸드오프가 있어야 한다. 이게 '문서 하네스 작동'의 핵심."""
    state = json.loads(STATE.read_text(encoding="utf-8"))
    if state.get("dirty") is False:
        # 이미 닫힌 상태라면 핸드오프가 있는 지금은 통과해야 한다
        assert checker_main(["--root", str(REPO)]) == 0, (
            "세션이 닫힌 상태인데 핸드오프가 없으면 실패해야 한다"
        )
        return
    # 진행 중이면, 닫힌 상태를 만들어 '핸드오프 없음'이 위반인지 확인한다
    root = tmp_path / "repo"
    (root / ".harness").mkdir(parents=True)
    (root / "docs").mkdir(parents=True)
    (root / ".harness/policy.json").write_text(
        (REPO / ".harness/policy.json").read_text(encoding="utf-8"), encoding="utf-8")
    closed = dict(state)
    closed["dirty"] = False
    (root / ".harness/state.json").write_text(
        json.dumps(closed, ensure_ascii=False, indent=2), encoding="utf-8")
    # 핸드오프 없이 닫힌 상태
    assert checker_main(["--root", str(root)]) == 1, (
        "세션이 닫혔는데 핸드오프 문서를 요구하지 않았다 — 문서 하네스가 작동하지 않는다"
    )
