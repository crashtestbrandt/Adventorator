import os
from pathlib import Path

import pytest

from Adventorator.config import load_settings


@pytest.fixture()
def isolated_tmpdir(tmp_path, monkeypatch):
    # Change CWD to a temp dir so config.toml and .env are local to the test
    monkeypatch.chdir(tmp_path)
    return tmp_path


def write_file(path: Path, content: str):
    path.write_text(content, encoding="utf-8")


def test_env_overrides_toml_for_llm_api_url(isolated_tmpdir, monkeypatch):
    # Given a config.toml with an LLM api_url
    write_file(
        isolated_tmpdir / "config.toml",
        """
        [app]
        env = "dev"

        [features]
        llm = true

        [llm]
        api_url = "http://from-toml:11434/api/chat"
        model_name = "llama3:in-toml"
        default_system_prompt = "toml prompt"
        """
    )

    # And a .env overriding the llm api url
    write_file(
        isolated_tmpdir / ".env",
        "\n".join(
            [
                "ENV=dev",
                "FEATURES_LLM=true",
                "LLM_API_URL=http://from-env:9999/api/chat",
                "LLM_MODEL_NAME=llama3:in-env",
                "LLM_DEFAULT_SYSTEM_PROMPT=env prompt",
                # Minimal Discord values to satisfy model schema if validated/accessed
                "DISCORD_PUBLIC_KEY=dummy",
            ]
        ),
    )

    settings = load_settings()

    assert settings.features_llm is True
    assert settings.llm_api_url == "http://from-env:9999/api/chat"
    assert settings.llm_model_name == "llama3:in-env"
    assert settings.llm_default_system_prompt == "env prompt"


def test_toml_used_when_env_absent(isolated_tmpdir):
    write_file(
        isolated_tmpdir / "config.toml",
        """
        [llm]
        api_url = "http://only-toml:11434/api/chat"
        model_name = "llama3:toml-only"
        default_system_prompt = "hello from toml"
        """
    )

    # Provide only the required Discord key via .env to satisfy Settings validation,
    # but do not provide any LLM-related env vars so TOML values should be used.
    write_file(
        isolated_tmpdir / ".env",
        "\n".join([
            "DISCORD_PUBLIC_KEY=dummy",
            "ENV=dev",
        ]),
    )

    settings = load_settings()

    assert settings.llm_api_url == "http://only-toml:11434/api/chat"
    assert settings.llm_model_name == "llama3:toml-only"
    assert settings.llm_default_system_prompt == "hello from toml"
