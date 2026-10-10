import pytest

from src.services.boss_cli import (
    BossCliIncompatible,
    BossCliInspection,
    build_boss_prefix,
    compatibility_problems,
    inspect_boss_cli,
    require_compatible_boss_cli,
    resolve_boss_cli,
)


def _compatible_inspection(executable: str = "/opt/tools/boss") -> BossCliInspection:
    return BossCliInspection(
        executable=executable,
        version="3.0.0",
        root_options=frozenset({"--cdp-url", "--json"}),
        search_options=frozenset({"--job-type", "--no-cache", "--city"}),
        login_options=frozenset({"--cdp", "--timeout"}),
    )


def test_resolve_boss_cli_supports_explicit_path_and_tilde(tmp_path, monkeypatch):
    binary = tmp_path / "boss"
    binary.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    binary.chmod(0o755)

    assert resolve_boss_cli(str(binary)) == str(binary.resolve())

    monkeypatch.setattr("src.services.boss_cli.shutil.which", lambda command: str(binary) if command == "boss" else None)
    assert resolve_boss_cli("boss") == str(binary.resolve())


def test_resolve_boss_cli_anchors_relative_path_to_project_root(tmp_path, monkeypatch):
    binary = tmp_path / ".tools" / "bin" / "boss"
    binary.parent.mkdir(parents=True)
    binary.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    binary.chmod(0o755)
    monkeypatch.setattr("src.services.boss_cli.PROJECT_ROOT", tmp_path)

    assert resolve_boss_cli("./.tools/bin/boss") == str(binary.resolve())


def test_inspection_reads_version_and_required_command_options(tmp_path, monkeypatch):
    binary = tmp_path / "boss"
    binary.write_text("", encoding="utf-8")
    binary.chmod(0o755)
    outputs = {
        ("--version",): "boss, version 3.0.0",
        ("--help",): """Options:
  --data-dir PATH
  --cdp-url TEXT
  --json / --no-json
  -h, --help
""",
        ("search", "--help"): """Options:
  --city TEXT
  --job-type TEXT
  --no-cache
""",
        ("login", "--help"): """Options:
  --cdp
  --timeout INTEGER
""",
    }

    class Completed:
        returncode = 0
        stderr = ""

        def __init__(self, stdout):
            self.stdout = stdout

    monkeypatch.setattr(
        "src.services.boss_cli._run_probe",
        lambda executable, *arguments: Completed(outputs[arguments]),
    )
    from src.services import boss_cli

    boss_cli._inspect_cached.cache_clear()
    inspection = inspect_boss_cli(str(binary))

    assert inspection.version == "3.0.0"
    assert compatibility_problems(inspection, browser_source="existing-browser") == []
    assert build_boss_prefix(
        inspection,
        browser_source="existing-browser",
        cdp_url="http://127.0.0.1:9222",
    ) == [
        str(binary.resolve()),
        "--cdp-url",
        "http://127.0.0.1:9222",
        "--json",
    ]
    boss_cli._inspect_cached.cache_clear()


def test_optional_browser_source_flag_is_only_passed_when_supported():
    inspection = BossCliInspection(
        executable="/opt/tools/boss",
        version="2.0.1",
        root_options=frozenset({"--browser-source", "--cdp-url", "--json"}),
        search_options=frozenset({"--job-type", "--no-cache", "--city"}),
        login_options=frozenset({"--cdp", "--timeout"}),
    )

    assert build_boss_prefix(
        inspection,
        browser_source="existing-browser",
        cdp_url="http://127.0.0.1:9222",
    ) == [
        "/opt/tools/boss",
        "--browser-source",
        "existing-browser",
        "--cdp-url",
        "http://127.0.0.1:9222",
        "--json",
    ]


def test_incompatible_cli_is_reported_before_login_or_search():
    inspection = BossCliInspection(
        executable="/opt/tools/boss",
        version="2.0.1",
        root_options=frozenset({"--cdp-url", "--json"}),
        search_options=frozenset(),
        login_options=frozenset({"--timeout"}),
    )

    problems = compatibility_problems(inspection, browser_source="existing-browser")
    assert "--city" in " ".join(problems)
    assert "--job-type" in " ".join(problems)
    with pytest.raises(BossCliIncompatible, match="检测版本 2.0.1"):
        require_compatible_boss_cli(inspection, browser_source="existing-browser")


def test_non_existing_browser_mode_is_not_accepted():
    problems = compatibility_problems(_compatible_inspection(), browser_source="auto")
    assert any("必须设置为 existing-browser" in problem for problem in problems)
