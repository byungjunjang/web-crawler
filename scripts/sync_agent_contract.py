"""scripts/sync_agent_contract.py — CLAUDE.md 와 AGENTS.md 의 실행 계약 블록을 동기화한다.

왜 이것이 필요한가 (2026-09-27 실측):

    CLAUDE.md 헤딩 29개 / AGENTS.md 헤딩 7개. 공유는 1개뿐이었다.
    `sync_domain_list.py --check` 와 `sync_codex_mirror.py --check` 는
    **AGENTS.md 에만** 적혀 있었다. 즉 Codex 는 커밋 전에 생성물 드리프트를 보고,
    Claude 는 보지 못했다. 같은 저장소를 다루는데 모델에 따라 검증 품질이 갈렸다.

이 문제는 산문으로 풀 수 없다. "두 파일에 같은 내용을 적어라" 는 지시는
안 지키면 조용히 어긋난다. 그래서 **단일 정본에서 두 파일을 생성**하고,
`--check` 로 드리프트를 CI 에서 잡는다. 저장소已有的 `sync_codex_mirror.py`·
`sync_domain_list.py` 와 같은 관례다.

**호스트 차이는 이 블록 밖에서 유지한다.** AGENTS.md 는 Windows PowerShell,
CLAUDE.md 는 macOS/Linux 로 셋업 절이 다르다. 그건 올바른 분업이다.
이 블록이 다룰 것은 **플랫폼과 무관하게 같아야 하는 것** — 검증 명령과,
완료를 선언하는 기준, 세션을 닫는 조건 — 뿐이다.

사용법:
    python scripts/sync_agent_contract.py           # 두 파일에 블록 기록
    python scripts/sync_agent_contract.py --check   # 드리프트 있으면 exit 1
"""
import argparse
import pathlib
import sys

REPO = pathlib.Path(__file__).resolve().parent.parent

BEGIN = "<!-- BEGIN GENERATED: agent-contract -->"
END = "<!-- END GENERATED: agent-contract -->"

# 두 지시 파일의 경로. 여기 적힌 파일이 없으면 아무것도 하지 않는다 —
# 없는 파일을 새로 만드는 것이 이 스크립트의 일이 아니다.
TARGETS = ("CLAUDE.md", "AGENTS.md")

CONTRACT_LINES = [
    "## 실행 계약 (모델 공통)",
    "",
    "이 절은 Claude Code, Codex, Cursor, Gemini CLI, 그 밖의 어떤 모델·도구에서",
    "작업하든 **똑같이** 지켜야 하는 부분이다. 두 파일 모두 아래 블록은",
    "`python scripts/sync_agent_contract.py` 로 같은 정본에서 생성된다.",
    "판단이 필요한 부분(무엇을 정할지)은 모델이 아니라 이 저장소의 파일이 정한다.",
    "",
    "> **아래 `python` 은 venv 안의 인터프리터다.** venv 밖에는 `python` 이 없을 수 있다",
    "> (macOS 는 `python3` 이고, 이 저장소实测 기준 `python` 은 `.venv/bin/python` 이다).",
    "> venv 를 먼저 활성화하거나, 없는 명령이 오면 곧바로 `python3` 로 되받아라.",
    ">",
    "> ```bash",
    "> python -m venv .venv && . .venv/bin/activate    # Windows: .\\.venv\\Scripts\\Activate.ps1",
    "> ```",
    "",
    "### 세션 시작",
    "",
    "1. `.harness/policy.json` 과 `.harness/state.json` 을 읽는다.",
    "   여기 없는 계획은 없다. 대화창에 남은 기억을 근거로 삼지 않는다.",
    "2. 작업이 `.harness/active_work` 와 다르면 새 작업으로 등록한다.",
    "",
    "### 제품 변경 전 (모두 실행하고, 실패하면 멈춘다)",
    "",
    "```text",
    "python -m pytest -q -k \"not e2e\"",
    "python scripts/continuity_check.py",
    "python scripts/sync_domain_list.py --check",
    "python scripts/sync_codex_mirror.py --check",
    "python scripts/sync_agent_contract.py --check",
    "python scripts/session_handoff.py --check",
    "```",
    "",
    "### 완료 선언",
    "",
    "- 위 다섯 명령이 **모두 exit 0** 이고, 그 출력을 본 뒤에만 완료라고 말한다.",
    "- 실행하지 않은 명령의 결과를 예상으로 쓰지 않는다. 모르면 `미확인` 이라고 쓴다.",
    "- 추측·추론을 결과로 보고하지 않는다. 실측 값과 그 출처를 함께 적는다.",
    "",
    "### 세션 종료",
    "",
    "1. **독립 리뷰**를 돌린다 (같은 모델이 아니라 다른 모델로).",
    "2. finding 을 **고친다**. 통과가 아니라 수정까지 끝낸다.",
    "3. `.harness/state.json` 의 `dirty` 를 `false` 로 바꾸고",
    "   `session_end.independent_review` 에 `status`(passed/findings_open)와",
    "   `model` 을 적는다. `dirty: false` 인데 이 기록이 없으면 검사기가 실패한다.",
    "4. `python scripts/session_handoff.py write` 로 핸드오프를 생성하고,",
    "   `python scripts/continuity_check.py` 를 다시 돌려 통과를 확인한다.",
    "",
    "### 변경 직후",
    "",
    "- TDD 는 RED 확인 → 최소 GREEN → 리팩터 순서다. RED 를 확인하지 않은 테스트는",
    "  통과한 것이 아니라 **아직 아무것도 검증하지 않은 것** 이다.",
]

CONTRACT_BLOCK = "\n".join((BEGIN, *CONTRACT_LINES, END))


def _find_block(text: str) -> str | None:
    if BEGIN not in text or END not in text:
        return None
    start = text.index(BEGIN)
    end = text.index(END) + len(END)
    return text[start:end]


def build(check_only: bool) -> int:
    drift = []
    for rel in TARGETS:
        path = REPO / rel
        if not path.exists():
            print(f"[sync_agent_contract] {rel} 없음 — 건너뛴다", file=sys.stderr)
            continue
        text = path.read_text(encoding="utf-8")
        existing = _find_block(text)
        if existing == CONTRACT_BLOCK:
            continue
        if check_only:
            state = "내용이 다름" if existing else "블록이 없음"
            drift.append(f"{rel}: {state}")
            continue
        if existing is None:
            # 블록이 없으면 맨 앞에 넣는다 — 계획 연속성 절보다 먼저 읽혀야 한다.
            new_text = f"{CONTRACT_BLOCK}\n\n{text.lstrip()}"
        else:
            new_text = text.replace(existing, CONTRACT_BLOCK, 1)
        path.write_text(new_text, encoding="utf-8")
        print(f"[sync_agent_contract] {rel} 갱신")

    if drift:
        print("[sync_agent_contract] 두 지시 파일의 실행 계약이 어긋나 있다:", file=sys.stderr)
        for item in drift:
            print(f"  - {item}", file=sys.stderr)
        print("  Fix: python scripts/sync_agent_contract.py", file=sys.stderr)
        return 1
    if not check_only:
        print("[sync_agent_contract] 실행 계약이 최신이다")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="CLAUDE.md/AGENTS.md 실행 계약 동기화")
    parser.add_argument("--check", action="store_true", help="드리프트가 있으면 exit 1")
    args = parser.parse_args(argv)
    return build(args.check)


if __name__ == "__main__":
    raise SystemExit(main())
