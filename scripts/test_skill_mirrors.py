"""Claude 정본에서 Codex/Work 스킬 미러가 함께 생성되는지 검증한다."""
from pathlib import Path

import sync_codex_mirror as mirrors


def test_official_and_legacy_mirror_locations_are_configured():
    configured = {(path.relative_to(mirrors.REPO_ROOT).as_posix(), token)
                  for path, token in mirrors.MIRRORS}
    assert configured == {
        (".agents/skills", ".agents/skills"),
        (".codex/skills", ".codex/skills"),
    }


def test_text_paths_are_rewritten_for_each_host():
    source = b"Read .claude/skills/web-crawler/SKILL.md"
    path = Path("SKILL.md")
    assert mirrors._transform_bytes(path, source, ".agents/skills") == (
        b"Read .agents/skills/web-crawler/SKILL.md"
    )
    assert mirrors._transform_bytes(path, source, ".codex/skills") == (
        b"Read .codex/skills/web-crawler/SKILL.md"
    )


def test_checked_in_mirrors_are_current():
    assert mirrors.check() == 0
