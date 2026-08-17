from pathlib import Path

from gptnt.ktane.state.module_registry import _load_module_registry


def test_empty_registry_uses_default_facts(tmp_path: Path) -> None:
    registry_path = tmp_path / "module_registry.yaml"
    _ = registry_path.write_text("", encoding="utf-8")

    registry = _load_module_registry(registry_path)

    assert registry.modules == {}
    assert not registry.needs_multiple_frames("UnknownModule")
