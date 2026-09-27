"""두 지시 파일(CLAUDE.md·AGENTS.md)이 **어느 모델에서 읽어도 같은 기준**을 내는지
검사한다.

왜 이 파일이 있는가 (2026-09-27 실측):

    CLAUDE.md 헤딩 29개 / AGENTS.md 헤딩 7개. 공유는 1개뿐이었다.
    `sync_domain_list.py --check` 와 `sync_codex_mirror.py --check` 는
    **AGENTS.md 에만** 적혀 있었다. Codex 는 커밋 전에 드리프트를 보고,
    Claude 는 보지 못했다. 같은 저장소를 다루는데 모델에 따라 검증 품질이 갈렸다.

"두 파일에 같은 내용을 적어라" 는 산문 지시로 풀 수 없다. 안 지키면 조용히
어긋나고 아무도 모른다. 그래서 **생성**(`sync_agent_contract.py`)으로 막고,
여기서는 그 생성이 실제로 성립하는지 — 그리고 블록에 적힌 명령이 **진짜 동작하는지** —
를 검사한다. 문서가 실행되지 않는 명령을 남기면 그건 계약이 아니라 장식이다.
"""
import pathlib
import re
import subprocess
import sys

import pytest

REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from sync_agent_contract import BEGIN, CONTRACT_BLOCK, END, TARGETS  # noqa: E402


def _blocks():
    out = {}
    for rel in TARGETS:
        text = (REPO / rel).read_text(encoding="utf-8")
        assert BEGIN in text and END in text, (
            f"{rel} 에 실행 계약 블록이 없다 — `python scripts/sync_agent_contract.py` 로 생성하라"
        )
        start = text.index(BEGIN)
        end = text.index(END) + len(END)
        out[rel] = text[start:end]
    return out


BLOCKS = _blocks()


# ── 1) 두 파일이 같은 내용을 담는가 ──────────────────────────────────────

def test_both_instruction_files_carry_the_contract():
    for rel, block in BLOCKS.items():
        assert block, f"{rel} 의 계약 블록이 비어 있다"


def test_contract_block_is_byte_identical_across_files():
    """모델이 무엇이든 같은 블록을 읽어야 한다."""
    values = set(BLOCKS.values())
    assert len(values) == 1, (
        "실행 계약 블록이 파일마다 다르다 — 어느 모델이 어떤 기준으로 일하는지 갈렸다\n"
        + "\n".join(f"  {rel}: {len(b)}자" for rel, b in BLOCKS.items())
    )


def test_contract_matches_its_single_source():
    """생성기가 지금 정본이라고 하는 것과 파일에 적힌 것이 같아야 한다."""
    assert set(BLOCKS.values()) == {CONTRACT_BLOCK}, (
        "파일의 계약 블록이 sync_agent_contract.py 의 정본과 다르다 — 생성기를 다시 돌려라"
    )


def test_sync_is_idempotent():
    """같은 버전을 두 번 돌려도 두 번째 diff 가 0 이어야 한다 (가이드 16절)."""
    proc = subprocess.run(
        [sys.executable, str(REPO / "scripts/sync_agent_contract.py"), "--check"],
        capture_output=True, text=True, cwd=REPO,
    )
    assert proc.returncode == 0, f"생성이 이미 최신이 아니다:\n{proc.stdout}\n{proc.stderr}"


def test_sync_check_detects_drift(tmp_path):
    """한 파일의 블록만 고치면 `--check` 가 잡는지 확인한다.

    실제로 고치지 않는다 — 복사본 fixture 로 `--root` 를 바꿔 시도하지 않고,
    대신 드리프트 감지 로직을 직접 검증한다. 이 검사가 고장나면 조용히 통과한다.
    """
    import sync_agent_contract as sac

    real_repo = sac.REPO
    try:
        for rel in TARGETS:
            path = real_repo / rel
            original = path.read_text(encoding="utf-8")
            tampered = original.replace("모두 exit 0", "모두 exit 1", 1)
            if tampered == original:
                pytest.skip(f"{rel} 에서 변이할 문자열을 못 찾았다")
            path.write_text(tampered, encoding="utf-8")
            try:
                assert sac.build(check_only=True) == 1, (
                    f"{rel} 의 계약 블록을 바꿨는데 --check 가 통과했다 — "
                    f"두 지시 파일이 갈려도 아무도 모른다"
                )
            finally:
                path.write_text(original, encoding="utf-8")
    finally:
        sac.REPO = real_repo
    # 복원 확인
    assert sac.build(check_only=True) == 0, "원복하지 못했다"


# ── 2) 블록의 명령이 진짜 동작하는가 ────────────────────────────────────

# 계약 블록 안에서 실행 명령 줄만 뽑는다. 인자(플래그·따옴표)가 붙어도 잡아야 한다.
_CONTRACT_LINE = re.compile(r"^python .+$", re.M)
CONTRACT_COMMANDS = [c.strip() for c in _CONTRACT_LINE.findall(CONTRACT_BLOCK)]

# 문서는 venv 활성화 후 실행을 전제한다. 이 저장소에는 `python` 이 없고 `python3` 와
# `.venv/bin/python` 만 있다(2026-09-27 실측). 그래서 계약을 그대로 복사해 돌릴 수 있는
# 형태로 검증한다 — venv 인터프리터로 같은 인자를 실행한다.
VENV_PYTHON = REPO / ".venv/bin/python"


def test_contract_assumes_activated_venv():
    """`python` 은 venv 안에서만 존재한다. 계약이 그 전제를 말하지 않으면 죽는다."""
    for needle in ("venv", "python3"):
        assert needle in CONTRACT_BLOCK, (
            f"계약에 {needle!r} 가 없다 — venv 밖에는 `python` 이 없어 명령이 죽는다"
        )


def test_contract_commands_are_runnable_with_venv_python():
    for rel in TARGETS:
        text = (REPO / rel).read_text(encoding="utf-8")
        assert "python scripts/continuity_check.py" in text, (
            f"{rel} 이 검사 명령을 가리키지 않는다"
        )


def test_contract_lists_the_five_verification_commands():
    """완료 선언의 근거가 되는 명령이 5개여야 한다 — 하나라도 빠지면 빈틈이다."""
    assert len(CONTRACT_COMMANDS) == 5, (
        f"계약 블록의 명령이 {len(CONTRACT_COMMANDS)}개다 (기대 5)\n{CONTRACT_COMMANDS}"
    )
    for required in ("-m pytest", "continuity_check.py", "sync_domain_list.py",
                     "sync_codex_mirror.py", "sync_agent_contract.py"):
        assert any(required in c for c in CONTRACT_COMMANDS), (
            f"계약에 `{required}` 가 없다 — 이 검사를 생략하면 드리프트를 커밋 전에 못 본다"
        )


@pytest.mark.parametrize("command", CONTRACT_COMMANDS)
def test_contract_command_actually_runs(command):
    """블록에 적힌 명령은 **실제로 exit 0** 이 되어야 한다.

    문서에 죽은 명령을 남기면 그건 계약이 아니라 장식이다.
    `python` 을 venv 인터프리터로 바꿔 같은 인자를 실행한다 — 문서가 전제하는
    "venv 활성화 후" 상황을 그대로 재현하는 것이기 때문이다.
    """
    if "-m pytest" in command:
        pytest.skip("pytest 는 현재 실행에서 이미 통과했다 — 두 번 돌릴 이유가 없다")
    assert VENV_PYTHON.exists(), (
        f"{VENV_PYTHON} 없다 — venv 인터프리터가 있어야 계약을 검증할 수 있다"
    )
    argv = [str(VENV_PYTHON)] + command.split()[1:]
    proc = subprocess.run(argv, capture_output=True, text=True, cwd=REPO)
    assert proc.returncode == 0, (
        f"계약 블록의 명령이 실패했다: `{command}`\n"
        f"exit={proc.returncode}\n{proc.stdout}\n{proc.stderr}\n"
        f"문서에서 지시한 대로 하면 죽는다 — 호출자를 고쳐라"
    )


def test_session_end_rule_is_in_the_contract():
    """세션 종료 규칙은 사용자가 세션마다 요구한 것이므로 계약에 있어야 한다."""
    for needle in ("독립 리뷰", "dirty", "findings_open"):
        assert needle in CONTRACT_BLOCK, f"계약에 {needle!r} 가 없다"
