"""scripts/session_handoff.py — 세션 종료 핸드오프 문서를 **생성**한다.

왜 생성기가 있는가 (2026-09-27 실측):

사람이 세션 문서를 쓰면 어긋난다. projects 전역 32개를 조사했을 때
`docs/handoff-*.md`(날짜명) 4개와 `docs/HANDOFF.md`(고정명) 3개가 갈라져 있었고,
그중 어느 것도 "지금 세션이 맞는지"를 기계적으로 확인하지 못했다.
`docstudio` 는 그 문제를 `session-close.mjs` 로 풀었다 — 세션 디렉터리와 루트 사본의
**바이트 일치**를 강제한다. 원리는 좋지만 12개 파일이라 이 저장소에는 과하다.

여기서는 같은 보장을 **생성**으로 얻는다. 정본은 `.harness/state.json` 하나이므로
문서는 언제나 정본과 일치한다 — 어긋날 수 없다. 사람이 고칠 곳이 없으니 드리프트도 없다.

가져온 것 (docstudio `agent-docs init/check` + `session-close.mjs` 의 원리)
- 정본에서 생성한다 (`init` = `write`)
- `--check` 로 최신 여부를 판정한다 (`check`)
- baseline(실측 결과)을 문서에 포함한다 (그들의 `baseline` 섹션 요구)
- 작업 도구(모델)를 기록한다 (재현성)

버린 것: `docs/sessions/<날짜>/` 디렉터리 6파일 × 2위치(12개). 파일 수가 곧
유지보수 비용이고, 이 저장소는 그 비용을 감당할 규모가 아니다. 근거는
`scripts/test_session_handoff.py` 머리말 참조.

사용법:
    python scripts/session_handoff.py write     # 생성
    python scripts/session_handoff.py --check   # 최신 아니면 exit 1
"""
import argparse
import hashlib
import json
import pathlib
import re
import shlex
import subprocess
import sys

REPO = pathlib.Path(__file__).resolve().parent.parent
HANDOFF_REL = "docs/session-handoff.md"
GENERATOR = "scripts/session_handoff.py"

# 세션 종료 전에 남겨야 하는 실측 명령. 이 저장소의 실행 계약이 정한 목록이다.
VERIFICATION_COMMANDS = [
    ("baseline", 'python -m pytest -q -k "not e2e"'),
    ("연속성", "python scripts/continuity_check.py"),
    ("도메인 목록", "python scripts/sync_domain_list.py --check"),
    ("Codex 미러", "python scripts/sync_codex_mirror.py --check"),
    ("실행 계약", "python scripts/sync_agent_contract.py --check"),
]

# 문서의 신선도를 판단하는 기준값. `write` 때 계산해 문서에 심고, `--check` 는
# 이것만 다시 계산해 비교한다.
#
# 왜 실측을 다시 돌리지 않는가: 실측에는 baseline(python -m pytest) 이 들어가고,
# pytest 는 이 저장소의 테스트를 수집하는데 그중 하나가 `--check` 를 호출한다.
# check 가 실측을 다시 하면 **pytest → check → render → pytest** 로 무한 재귀한다.
# 그래서 "실측"은 write 시점 한 번, "신선도"는 다이제스트 비교로 분리한다.
DIGEST_LABEL = "입력 다이제스트"


def _argv(command: str) -> list[str]:
    """계약 명령을 실행 argv 로 바꾼다.

    `str.split()` 은 **따옴표를 존중하지 않는다** — `-k "not e2e"` 가
    `['-k', '"not', 'e2e"']` 로 쪼개져 pytest 가 "no tests ran" 을 낸다.
    그 상태로 문서를 생성하면 **틀린 통과 수**가 다음 세션에 전달된다.
    """
    return [sys.executable] + shlex.split(command)[1:]


def _run(cmd: list[str], cwd: pathlib.Path) -> tuple[int, str]:
    proc = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd)
    tail = (proc.stdout or proc.stderr).strip().splitlines()
    return proc.returncode, (tail[-1] if tail else "")


def _stable(text: str) -> str:
    """휘발 값을 지운 요약 — 경과 시간 같은 것은 멱등성을 깨고 무의미하다.

    pytest 의 "in 8.12s" 가 매 실행마다 달라서, 그대로 적으면 `write` 를 두 번
    돌릴 때마다 diff 가 나고 커밋된 문서가 즉시 낡는다(리뷰 [D2]).
    """
    text = re.sub(r"\s*in [0-9.]+s\b", "", text)
    return re.sub(r"\s+", " ", text)[:70]


def _git(*args: str, cwd: pathlib.Path) -> str:
    proc = subprocess.run(["git", *args], capture_output=True, text=True, cwd=cwd)
    return proc.stdout.strip() if proc.returncode == 0 else ""


def input_digest(root: pathlib.Path) -> str:
    """핸다이제스트 — 문서의 **입력**(정본 상태)만으로 만든다.

    ⚠ git HEAD 를 넣으면 안 된다. 2026-09-27 독립 리뷰가 잡은 [High] 결함:
    HEAD 를 담으면 "다이제스트가 든 파일을 커밋하는" 행위가 HEAD 를 바꿔
    그 다이제스트를 즉시 무효화한다. amend 도 커밋 해시를 바꾸므로
    **고정점이 존재하지 않는다** — 아무리 재생성해도 다음 커밋에서 또 어긋난다.
    커밋해도 무효화되지 않는 것은 **문서의 입력**뿐이다.
    """
    state = (root / ".harness/state.json").read_text(encoding="utf-8")
    policy = (root / ".harness/policy.json").read_text(encoding="utf-8")
    return hashlib.sha256(f"{state}\x00{policy}".encode("utf-8")).hexdigest()


_TABLE_ROW = re.compile(r"^\|\s*(baseline|연속성|도메인 목록|Codex 미러|실행 계약)\s*\|")


def previous_rows(root: pathlib.Path) -> dict[str, str]:
    """디스크의 **이전 문서**에서 실측 표의 *결과 칸*만 읽는다.

    왜 이게 필요한가 (2026-10-01 실측 재현):
    `write` 의 1패스가 실측 표를 비우면 그 산출물이 디스크에 놓이는 동안
    `test_handoff_quotes_actual_command_results` 가 그 자리에서 실패하고,
    2패스가 **거짓 exit=1** 을 기록한다. 실측: 문서 `exit=1 — 1 failed` /
    즉시 baseline `577 passed`. 순환이 성립한다.
    이전 표를 살리면 1패스 산출물에도 통과 수가 남으므로 자기참조가 통과한다.

    **결과 칸만** 읽고 명령 칸은 버린다 (2026-10-01 독립 리뷰 [Low]).
    행을 통째로 복사하면 계약 명령이 바뀐 뒤에도 옛 문자열을 되살린다 —
    명령 칸은 `render` 가 현재 `VERIFICATION_COMMANDS` 로 재구성한다.
    """
    target = root / HANDOFF_REL
    if not target.exists():
        return {}
    rows: dict[str, str] = {}
    for line in target.read_text(encoding="utf-8").splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) == 3 and _TABLE_ROW.match(line.strip()) and cells[2]:
            rows[cells[0]] = cells[2]
    return rows


# 인용한 값이 **이전 실행**의 것임을 표에 박는다 (2026-10-01 독립 리뷰 [High]).
# 표시가 없으면 "측정 시점 HEAD: <현재>" 아래에 더 오래된 통과 수가 지금
# 측정한 것처럼 놓여 사람이 오독한다.
CARRIED_PREFIX = "(이전 실행) "


def render(root: pathlib.Path, run_verification: bool) -> str:
    """정본(state.json)과 git 실측으로 핸드오프 본문을 만든다.

    ⚠ 순수하지 **않다** (2026-10-01 독립 리뷰 [High] 로 정정).
    `run_verification=True` 는 `state/policy/git` 만 읽어 순수하지만,
    `run_verification=False`(1패스)는 **디스크의 이전 문서**에서 실측 표를
    가져온다. 두 번째 입력은 `input_digest` 가 추적하지 않으므로
    "같은 입력이면 같은 출력"은 1패스에서 성립하지 않는다.
    그래도 `--check` 가 안전한 이유: `--check` 는 `render` 를 부르지 않고
    다이제스트(`state`+`policy`)만 비교한다. 그리고 최종 문서는 2패스가 쓴다.

    1패스는 실측을 **다시 돌리지 않고** 이전 표의 결과 칸을 인용한다
    (`CARRIED_PREFIX` 로 출처를 표시). 표가 비면 빈 칸으로 둔다.
    """
    state = json.loads((root / ".harness/state.json").read_text(encoding="utf-8"))
    policy = json.loads((root / ".harness/policy.json").read_text(encoding="utf-8"))
    review = (state.get("session_end") or {}).get("independent_review") or {}
    model = review.get("model") or "미기록 (독립 리뷰 미실행)"

    head = _git("rev-parse", "--short", "HEAD", cwd=root) or "?"
    branch = _git("rev-parse", "--abbrev-ref", "HEAD", cwd=root) or "?"
    work = policy.get("active_work", {})
    ns = policy.get("north_star", {})

    lines = [
        "# 세션 핸드오프",
        "",
        "> 이 파일은 **생성물**이다. `python scripts/session_handoff.py write` 로 만든다.",
        ">",
        "> `--check` 가 잡는 것: **정본(state/policy)이 바뀌었는데 문서가 따라가지 않은 것**.",
        "> `--check` 가 **못** 잡는 것: 이 본문 안의 문장을 손으로 고치는 것.",
        "> 정본이 아닌 본문은 사람이 읽는 설명일 뿐이라 기계가 검증할 수 없다.",
        f"> 정본은 `.harness/state.json` 이고, 생성기는 `{GENERATOR}` 다.",
        "",
        "다음 세션은 이 파일과 `.harness/state.json` 만 읽으면 된다. "
        "이전 대화 이력은 근거가 아니다.",
        "",
        f"- {DIGEST_LABEL}: `{input_digest(root)}`",
        "",
        "## 상태 한 줄 요약",
        "",
        f"- 활성 작업: **{work.get('id', '?')}** — 계약 `{work.get('contract_path', '?')}`",
        f"- NORTH STAR: {ns.get('statement', '?')} (`{ns.get('id', '?')}`)",
        f"- 단계: `{state.get('stage', '?')}` / dirty=`{state.get('dirty')}`",
        f"- 검증 커밋: `{state.get('verified_commit') or '미기록'}`",
        f"- 작업 도구: **{model}**",
        "",
        "## 실측 검증 (write 시점에 돌린 결과다)",
        "",
        f"측정 시점 HEAD: `{head}` · 브랜치 `{branch}`",
        "",
        "> ⚠ **출처**: 아래 결과는 이 문서를 커밋하기 **전의 작업 트리**에서 돌았다.",
        "> `write` 는 커밋 전에 불리므로 위 해시는 이 문서를 담는 커밋의 **부모**다.",
        "> 그래서 그 커밋을 체크아웃해 `baseline` 을 다시 돌리면 통과 수가 **다를 수 있다** —",
        "> 아래 수는 '이 커밋의 트리'가 아니라 '그 커밋 직전의 작업 트리'의 실측이다.",
        "> 이 문서를 커밋한 다음 다시 생성하면(HEAD 가 바뀐다) 수치가 맞춰진다.",
        "",
        "| 항목 | 명령 | 결과 |",
        "|---|---|---|",
    ]
    carried = previous_rows(root) if not run_verification else {}
    for label, command in VERIFICATION_COMMANDS:
        if run_verification:
            code, tail = _run(_argv(command), cwd=root)
            verdict = "exit=0 ✅" if code == 0 else f"exit={code} ❌"
            detail = _stable(tail) or "출력 없음"
            lines.append(f"| {label} | `{command}` | {verdict}{' — ' + detail if detail else ''} |")
        elif label in carried:
            # 이전 문서의 **결과 칸**을 인용한다. 명령 칸은 현재 값으로 재구성하고
            # 출처 표시를 붙인다 — 다이제스트만 갱신되는 1패스.
            lines.append(f"| {label} | `{command}` | {CARRIED_PREFIX}{carried[label]} |")
        else:
            # 이전 표가 없다(최초 생성). 빈 칸 — 숫자를 지어내지 않는다.
            lines.append(f"| {label} | `{command}` | (이전 실측 없음) |")

    lines += [
        "",
        "## 이번 세션에 한 일",
        "",
    ]
    log = _git("log", "--oneline", "-12", cwd=root)
    if log:
        lines += [f"- {line}" for line in log.splitlines()]
    else:
        lines.append("- (git 기록 없음)")

    lines += [
        "",
        "## 남은 것 / 다음 세션",
        "",
        f"- 활성 계약의 미해결 항목을 먼저 본다: `{work.get('contract_path', '?')}`",
        "- UNVERIFIED 로 남아 있는 것은 지어내지 말고 그대로 유지한다.",
        "- 세션 문맥의 정본은 `.harness/state.json` 하나다 — 중간에 멈췄다면 그 파일을 "
        "갱신한다 (ADR-001). 정본 밖에 파생 사본을 두지 않는다 (AGENTS.md).",
        "",
        "## 다음 세션 즉시 시작",
        "",
        "```text",
        f"세션 이어받기. 프로젝트: {root}",
        f"먼저 {HANDOFF_REL} 와 .harness/state.json 을 읽는다.",
        f"그리고 baseline 확인: {VERIFICATION_COMMANDS[0][1]}  (위 표의 통과 수와 같아야 한다)",
        f"활성 작업: {work.get('id', '?')} — 계약 {work.get('contract_path', '?')}",
        "```",
        "",
    ]
    return "\n".join(lines)


def write(root: pathlib.Path) -> int:
    """2패스로 쓴다. 1패스는 **다이제스트만** 갱신하고 2패스는 실측까지 한다.

    왜 2패스인가 (2026-09-28 독립 리뷰 finding, 재현 확인):
    `render(run_verification=True)` 는 baseline 으로 pytest 를 돌리는데,
    그 안의 `test_check_passes_against_committed_handoff` 가 `session_handoff --check` 를
    호출한다. 그런데 그 시점에 디스크의 핸드오프는 **옛 다이제스트**다 — `write` 는
    아직 아무것도 쓰기 전이다. 그래서 그 검사(와 인접한 실측 수치 검사)가 실패하고,
    문서에 `exit=1 ❌` 가 **참이 아닌 값**으로 기록된다.

    ⚠ 1패스가 실측 표까지 **비우면** 이 수정은 절반만 된다 (2026-10-01 실측).
    표가 빈 문서가 디스크에 있는 동안 `test_handoff_quotes_actual_command_results` 가
    거기서 실패하고, 2패스는 그대로 `exit=1 — 1 failed` 를 적는다. 즉시 돌린 실제
    baseline 은 `577 passed` 였다. 그래서 1패스는 `previous_rows()` 로 **이전 표를
    살려** 쓴다 — 유일한 차이는 다이제스트다.
    """
    target = root / HANDOFF_REL
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(render(root, run_verification=False), encoding="utf-8")
    target.write_text(render(root, run_verification=True), encoding="utf-8")
    print(f"[session_handoff] {HANDOFF_REL} 생성 (실측 포함, 2패스)")
    return 0


def check(root: pathlib.Path) -> int:
    target = root / HANDOFF_REL
    if not target.exists():
        print(f"[session_handoff] {HANDOFF_REL} 없다 — `python {GENERATOR} write` 로 생성하라",
              file=sys.stderr)
        return 1
    # 실측을 다시 돌리지 않는다 — 재귀 위험. 대신 정본 지문을 비교한다.
    recorded = re.search(
        rf"- {re.escape(DIGEST_LABEL)}: `([0-9a-f]{{64}})`",
        target.read_text(encoding="utf-8"),
    )
    if not recorded:
        print(f"[session_handoff] {HANDOFF_REL} 에 {DIGEST_LABEL} 가 없다 — 재생성하라",
              file=sys.stderr)
        return 1
    current = input_digest(root)
    if recorded.group(1) != current:
        print(
            f"[session_handoff] {HANDOFF_REL} 이 현재 정본과 어긋난다\n"
            f"  문서: {recorded.group(1)[:16]}…\n"
            f"  현재: {current[:16]}…\n"
            f"  Fix: python {GENERATOR} write",
            file=sys.stderr,
        )
        return 1
    print(f"[session_handoff] {HANDOFF_REL} 최신")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="세션 종료 핸드오프 문서 생성/검사")
    parser.add_argument("command", nargs="?", default="check", choices=["write", "check"])
    parser.add_argument("--check", action="store_true", help="기본값과 같음 (하위 호환)")
    parser.add_argument("--root", default=str(REPO))
    args = parser.parse_args(argv)
    root = pathlib.Path(args.root).resolve()
    if not (root / ".harness/state.json").exists():
        print(f"하네스 미설치 — {root}/.harness/state.json 없다", file=sys.stderr)
        return 2
    return write(root) if args.command == "write" else check(root)


if __name__ == "__main__":
    raise SystemExit(main())
