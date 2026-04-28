from pathlib import Path

from app.browser import _legacy as browser_legacy


def test_resolve_chrome_binary_path_uses_chrome_bin_env(monkeypatch, tmp_path):
    """
    容器环境应优先使用 CHROME_BIN 指向的 Chromium 可执行文件。

    AI by zb
    """
    chrome_binary = tmp_path / "chromium"
    chrome_binary.write_text("", encoding="utf-8")
    monkeypatch.setenv("CHROME_BIN", str(chrome_binary))
    monkeypatch.delenv("CHROMIUM_BIN", raising=False)

    assert browser_legacy._resolve_chrome_binary_path() == str(Path(chrome_binary))
