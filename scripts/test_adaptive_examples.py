"""문서의 자가치유 코드를 로컬 HTML로 그대로 실행한다."""
from pathlib import Path
import gc
import re
import sqlite3

import pytest
from scrapling.parser import Selector
from scrapling.core.storage import SQLiteStorageSystem

import utils

REPO = Path(__file__).resolve().parents[1]
EXAMPLES = [
    (".claude/skills/web-crawler/SKILL.md", "### 셀렉터 자가 치유"),
    ("scripts/scrapling_reference.md", "## 8. 셀렉터 자가 치유"),
]


@pytest.fixture(autouse=True)
def isolated_storage_cache():
    SQLiteStorageSystem.cache_clear()
    yield
    SQLiteStorageSystem.cache_clear()
    gc.collect()


@pytest.mark.parametrize("file,heading", EXAMPLES)
@pytest.mark.parametrize("failure", [None, "mkdir", "init", "save", "heal"])
def test_storage_failures_fall_back_without_network(file, heading, failure, monkeypatch, tmp_path):
    text = (REPO / file).read_text(encoding="utf-8").split(heading, 1)[1]
    block = re.search(r"```python\n(.*?)```", text, re.S).group(1)
    block = block.replace("<URL>", "https://example.com").replace("<SELECTOR>", "div.item")
    monkeypatch.chdir(tmp_path)
    pages = []
    configs = []
    def offline_get(url, selector_config):
        configs.append(selector_config)
        if failure == "init" and selector_config["adaptive"]:
            raise sqlite3.OperationalError("cannot open database")
        page = Selector("<div class='item'>Product</div>", url=url, **selector_config)
        pages.append(page)
        return page
    monkeypatch.setattr(utils, "plain_get", offline_get)
    if failure == "mkdir":
        monkeypatch.setattr(Path, "mkdir", lambda *a, **kw: (_ for _ in ()).throw(PermissionError()))
    if failure == "save":
        monkeypatch.setattr(SQLiteStorageSystem.__wrapped__, "save",
                            lambda *a, **kw: (_ for _ in ()).throw(sqlite3.OperationalError("locked")))
    if failure == "heal":
        original_css = Selector.css
        def css(self, selector, **kwargs):
            if kwargs.get("adaptive"):
                raise sqlite3.OperationalError("locked")
            return original_css(self, selector, **kwargs)
        monkeypatch.setattr(Selector, "css", css)
    try:
        scope = {"__name__": "document_example"}
        exec(compile(block, file, "exec"), scope)
        assert scope["items"][0].css("::text").get() == "Product"
        assert any(not config["adaptive"] for config in configs) is bool(failure)
        if failure:
            assert "storage_args" not in configs[-1]
    finally:
        scope.clear()
        pages.clear()


@pytest.mark.parametrize("file,heading", EXAMPLES)
def test_documented_healing_recovers_changed_html(file, heading, monkeypatch, tmp_path):
    text = (REPO / file).read_text(encoding="utf-8").split(heading, 1)[1]
    block = re.search(r"```python\n(.*?)```", text, re.S).group(1)
    block = block.replace("<URL>", "https://example.com").replace("<SELECTOR>", "div.item")
    monkeypatch.chdir(tmp_path)
    pages = []
    def offline_get(url, selector_config):
        name = "item" if not pages else "product"
        page = Selector(f"<div class='{name}'>Product</div>", url=url, **selector_config)
        pages.append(page)
        return page
    monkeypatch.setattr(utils, "plain_get", offline_get)
    try:
        scope = {"__name__": "document_example"}
        exec(compile(block, file, "exec"), scope)
        assert scope["items"][0].attrib["class"] == "product"
    finally:
        scope.clear()
        pages.clear()
